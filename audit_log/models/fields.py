from django.db import models
from django.contrib.auth.models import User
from audit_log import registration

class LastUserField(models.ForeignKey):
    """
    A field that keeps the last user that saved an instance
    of a model. None will be the value for AnonymousUser.
    """

    def __init__(self, to=User, null = True, **kwargs):
        super(LastUserField, self).__init__(to = to, null = True, **kwargs)

    def contribute_to_class(self, cls, name):
        super(LastUserField, self).contribute_to_class(cls, name)
        registry = registration.FieldRegistry(self.__class__)
        registry.add_field(cls, self)

    def south_field_triple(self):
        "Returns a suitable description of this field for South."
        # We'll just introspect ourselves, since we inherit.
        from south.modelsinspector import introspector
        field_class = "django.db.models.fields.related.ForeignKey"
        args, kwargs = introspector(self)
        return (field_class, args, kwargs)


class LastIPField(models.IPAddressField):
    """
    A field that keeps the last ip that touched an instance
    of a model.
    """

    def __init__(self, null=True, **kwargs):
        super(LastIPField, self).__init__(null=null, **kwargs)

    def contribute_to_class(self, cls, name):
        super(LastIPField, self).contribute_to_class(cls, name)
        registry = registration.FieldRegistry(self.__class__)
        registry.add_field(cls, self)


# taken from http://south.aeracode.org/ticket/693
try:
    # Try and import the field so we can see if audit_log is available
    from south.modelsinspector import add_introspection_rules

    # Make sure the `to` and `null` parameters will be ignored
    rules = [(
        (LastUserField,),
        [],
        {
            'to': ['rel.to', {'default': User}],
            'null': ['null', {'default': True}],
        },
    )]

    # Add the rules for the `LastUserField`
    add_introspection_rules(
        rules,
        ['^audit_log\.models\.fields\.LastUserField'],
    )
except ImportError:
    pass
