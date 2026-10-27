from django.contrib.auth.forms import (
    AdminPasswordChangeForm as BaseAdminPasswordChangeForm,
    AdminUserCreationForm as BaseAdminUserCreationForm,
    UserChangeForm as BaseUserChangeForm,
)

from .models import User
from .role_groups import GROUP_NAME_TO_ROLE, validate_role_combination


def _validate_groups_field(groups):
    if not groups:
        return groups
    roles = {
        GROUP_NAME_TO_ROLE[g.name]
        for g in groups
        if g.name in GROUP_NAME_TO_ROLE
    }
    validate_role_combination(roles)
    return groups


class UserCreationForm(BaseAdminUserCreationForm):
    class Meta(BaseAdminUserCreationForm.Meta):
        model = User
        fields = ('username',)

    def clean_groups(self):
        return _validate_groups_field(self.cleaned_data.get('groups'))


class UserChangeForm(BaseUserChangeForm):
    class Meta(BaseUserChangeForm.Meta):
        model = User
        fields = '__all__'

    def clean_groups(self):
        return _validate_groups_field(self.cleaned_data.get('groups'))


class AdminPasswordChangeForm(BaseAdminPasswordChangeForm):
    pass
