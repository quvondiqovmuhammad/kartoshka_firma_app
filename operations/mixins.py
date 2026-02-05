from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect

class RoleRequiredMixin(LoginRequiredMixin):
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        user_role = getattr(request.user, 'role', None)  # foydalanuvchining role maydoni

        if self.allowed_roles and user_role not in self.allowed_roles:
            return redirect('no_permission')  # bu siz yaratgan 403 yoki bosh sahifa bo'lishi mumkin

        return super().dispatch(request, *args, **kwargs)
