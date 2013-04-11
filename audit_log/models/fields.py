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
