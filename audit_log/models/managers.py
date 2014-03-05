import sys
import copy
from django.utils import timezone as datetime
from django.db import models
from django.utils.functional import curry
from django.utils.translation import ugettext_lazy as _

from audit_log.models.fields import LastUserField, LastIPField


ACTION_TYPES = (
    ('I', _('Created')),
    ('U', _('Changed')),
    ('D', _('Deleted')),
)

# Oh
models.options.DEFAULT_NAMES += ('auditlog_properties',)


class ItemLockedError(Exception):
    def __init__(self, model):
        self.value = '%s instance is locked' % model.__class__.__name__
    def __str__(self):
        return repr(self.value)


class LogEntryObjectDescriptor(object):
    def __init__(self, model):
        self.model = model

    def __get__(self, instance, owner):
        kwargs = dict((f.attname, getattr(instance, f.attname))
                    for f in self.model._meta.fields
                    if hasattr(instance, f.attname))
        return self.model(**kwargs)


class AuditLogManager(models.Manager):
    def __init__(self, model, instance = None):
        super(AuditLogManager, self).__init__()
        self.model = model
        self.instance = instance

    def get_query_set(self):
        if self.instance is None:
            return super(AuditLogManager, self).get_query_set()

        f = {self.instance._meta.pk.name: self.instance.pk}
        return super(AuditLogManager, self).get_query_set().filter(**f)

    def is_locked(self):
        return AuditLog.is_locked(self.instance)

    def lock(self):
        return AuditLog.lock(self.instance)

    def unlock(self):
        return AuditLog.unlock(self.instance)


class AuditLogDescriptor(object):
    def __init__(self, model, manager_class):
        self.model = model
        self._manager_class = manager_class

    def __get__(self, instance, owner):
        if instance is None:
            return self._manager_class(self.model)
        return self._manager_class(self.model, instance)


class AuditLog(object):
    manager_class = AuditLogManager

    def __init__(self, exclude=[]):
        self._exclude = exclude

    def contribute_to_class(self, cls, name):
        self.manager_name = name
        models.signals.class_prepared.connect(self.finalize, sender=cls)


    def create_log_entry(self, instance, action_type):
        manager = getattr(instance, self.manager_name)
        attrs = {}
        for field in instance._meta.fields:
            if field.attname not in self._exclude:
                attrs[field.attname] = getattr(instance, field.attname)
        manager.create(action_type=action_type, **attrs)

    def post_save(self, instance, created, **kwargs):
        self.create_log_entry(instance, created and 'I' or 'U')


    def post_delete(self, instance, **kwargs):
        self.create_log_entry(instance, 'D')

    def pre_save(self, instance, **kwargs):
        if self.is_locked(instance):
            raise ItemLockedError(instance)

    def pre_delete(self, instance, **kwargs):
        if self.is_locked(instance):
            raise ItemLockedError(instance)

    def finalize(self, sender, **kwargs):
        log_entry_model = self.create_log_entry_model(sender)

        models.signals.pre_save.connect(self.pre_save, sender=sender, weak=False)
        models.signals.pre_delete.connect(self.pre_delete, sender=sender, weak=False)

        models.signals.post_save.connect(self.post_save, sender=sender, weak=False)
        models.signals.post_delete.connect(self.post_delete, sender=sender, weak=False)

        descriptor = AuditLogDescriptor(log_entry_model, self.manager_class)
        setattr(sender, self.manager_name, descriptor)

    def copy_fields(self, model):
        """
        Creates copies of the fields we are keeping
        track of for the provided model, returning a
        dictionary mapping field name to a copied field object.
        """
        fields = {'__module__': model.__module__}

        for field in model._meta.fields:

            if not field.name in self._exclude:

                field = copy.deepcopy(field)

                if isinstance(field, models.AutoField):
                    #we replace the AutoField of the original model
                    #with an IntegerField because a model can
                    #have only one autofield.

                    field.__class__ = models.IntegerField
                #Apply patch for 1:1 field issue ref: https://github.com/Atomidata/django-audit-log/issues/7
                if isinstance(field, models.OneToOneField):
                    field.__class__ = models.ForeignKey

                if field.primary_key:
                    field.serialize = True

                if field.primary_key or field.unique:
                    #unique fields of the original model
                    #can not be guaranteed to be unique
                    #in the audit log entry but they
                    #should still be indexed for faster lookups.

                    field.primary_key = False
                    field._unique = False
                    field.db_index = True

                if field.rel and field.rel.related_name:
                    field.rel.related_name = '_auditlog_%s' % field.rel.related_name

                fields[field.name] = field

        if hasattr(model._meta, 'auditlog_properties'):
            for value in model._meta.auditlog_properties:
                fields[value] = getattr(model, value)

        return fields


    def get_logging_fields(self, model):
        """
        Returns a dictionary mapping of the fields that are used for
        keeping the acutal audit log entries.
        """
        rel_name = '_%s_audit_log_entry' % model._meta.object_name.lower()

        def entry_instance_to_unicode(log_entry):
            try:
                result = u'%s: %s %s at %s' % (model._meta.object_name,
                                               log_entry.object_state,
                                               log_entry.get_action_type_display().lower(),
                                               log_entry.action_date,

                )
            except AttributeError:
                result = u'%s %s at %s' % (model._meta.object_name,
                                           log_entry.get_action_type_display().lower(),
                                           log_entry.action_date

                )
            return result

        return {
            'action_id': models.AutoField(primary_key=True),
            'action_date': models.DateTimeField(auto_now_add=True),
            'action_user': LastUserField(related_name=rel_name),
            'action_type': models.CharField(max_length=1, choices=ACTION_TYPES),
            'action_ip': LastIPField(),
            'locked': models.NullBooleanField(),
            'object_state': LogEntryObjectDescriptor(model),
            '__unicode__': entry_instance_to_unicode,
        }

    def get_meta_options(self, model):
        """
        Returns a dictionary of fields that will be added to
        the Meta inner class of the log entry model.
        """
        return {
            'ordering': ('-action_date', 'action_id'),
            'app_label': model._meta.app_label,
            'get_latest_by': 'action_date',
        }

    def create_log_entry_model(self, model):
        """
        Creates a log entry model that will be associated with
        the model provided.
        """

        attrs = self.copy_fields(model)
        attrs.update(self.get_logging_fields(model))
        attrs.update(Meta=type('Meta', (), self.get_meta_options(model)))
        name = '%sAuditLogEntry' % model._meta.object_name
        model = type(name, (models.Model,), attrs)
        # Like a hack
        module = sys.modules[model.__module__]
        if not hasattr(module, name):
            setattr(module, name, model)
        return model

    @classmethod
    def _lock_toggle(cls, instance, val):
        try:
            ins = instance.audit_log.filter(**{instance._meta.pk.name: instance.pk}).latest()
        except:
            return False
        ins.locked = val
        ins.save(update_fields=['locked'])
        return True

    @classmethod
    def lock(cls, instance):
        return cls._lock_toggle(instance, True)

    @classmethod
    def unlock(cls, instance):
        return cls._lock_toggle(instance, False)

    @classmethod
    def is_locked(self, instance):
        #FIXME: allways return false on pk changes
        try:
            return instance.audit_log.filter(**{instance._meta.pk.name: instance.pk}).latest().locked
        except:
            return False
