from django.db.models import signals
from django.utils.functional import curry

from audit_log import registration
from audit_log.models import fields

VALID_METHODS = ('POST', 'PUT', 'DELETE')


class UserLoggingMiddleware(object):
    def process_request(self, request):
        if request.method in VALID_METHODS:
            if hasattr(request, 'user') and request.user.is_authenticated():
                user = request.user
            else:
                user = None

            update_arg = curry(self.update_arg, user, request)
            signals.pre_save.connect(update_arg, dispatch_uid = (self.__class__, request), weak=False)

    def process_response(self, request, response):
        signals.pre_save.disconnect(dispatch_uid = (self.__class__, request))
        return response

    def update_arg(self, user, request, sender, instance, **kwargs):
        self.update_users(user, sender, instance, **kwargs)
        self.update_request_data(request, sender, instance, **kwargs)

    def update_users(self, user, sender, instance, **kwargs):
        if user is None:
            return
        self._update_args(user, fields.LastUserField, sender, instance, **kwargs)

    def update_request_data(self, request, sender, instance, **kwargs):
        for arg, field in self._strip_request(request): #update request args
            self._update_args(arg, field, sender, instance, **kwargs)

    def _update_args(self, arg, field_type, sender, instance, **kwargs):
        registry = registration.FieldRegistry(field_type)
        if sender in registry:
            for field in registry.get_fields(sender):
                setattr(instance, field.name, arg)

    def _strip_request(self, request):
        """
        Takes a request object and returns the dictionary items we want to store.
        """
        ip = self._get_client_ip(request)
        return [(ip, fields.LastIPField)]

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
