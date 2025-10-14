from django.urls import path
from . import views

app_name = 'micboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/data/', views.data_json, name='data_json'),
    path('api/config/', views.ConfigHandler.as_view(), name='config_update'),
    path('api/group/', views.GroupUpdateHandler.as_view(), name='group_update'),
    path('api/discover/', views.api_discover, name='api_discover'),
    path('api/refresh/', views.api_refresh, name='api_refresh'),
    path('about/', views.about, name='about'),
]