from django.db import models
from django.conf import settings
from audit_log import registration

try:
    # Django 1.5+
    user_model = settings.AUTH_USER_MODEL
except AttributeError:
    # Django < 1.5
    from django.contrib.auth.models import User
    user_model = User


class LastUserField(models.ForeignKey):
    """
    A field that keeps the last user that saved an instance
    of a model. None will be the value for AnonymousUser.
    """
    
    def __init__(self, to = user_model, null = True,  **kwargs):
        super(LastUserField, self).__init__(to = to, null = null, **kwargs)
    
    def contribute_to_class(self, cls, name):
        super(LastUserField, self).contribute_to_class(cls, name)
        registry = registration.FieldRegistry(self.__class__)
        registry.add_field(cls, self)


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
    ),(
        (LastIPField,),
        [],
        {
            'null': ['null', {'default': True}],
        },
    )]

    # Add the rules for the `LastUserField`
    add_introspection_rules(
        rules,
        ['^audit_log\.models\.fields\.LastUserField',
        '^audit_log\.models\.fields\.LastIPField'],
    )


except ImportError:
    pass
