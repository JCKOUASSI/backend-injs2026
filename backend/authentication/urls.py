from django.urls import path

from . import views

urlpatterns = [
    path('login/', views.login_view, name='auth-login'),
    path('mfa/verify/', views.mfa_verify_view, name='auth-mfa-verify'),
    path('mfa/setup/', views.mfa_setup_view, name='auth-mfa-setup'),
    path('mfa/confirm/', views.mfa_confirm_view, name='auth-mfa-confirm'),
    path('mfa/disable/', views.mfa_disable_view, name='auth-mfa-disable'),
    path('token/refresh/', views.CookieTokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', views.logout_view, name='auth-logout'),
    path('me/', views.me_view, name='auth-me'),
    path('roles/', views.roles_view, name='auth-roles'),
    path('capabilities/', views.capabilities_view, name='auth-capabilities'),
    path('me/change-password/', views.change_password_view, name='auth-change-password'),
    path('users/', views.UserListCreateView.as_view(), name='user-list'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
]
