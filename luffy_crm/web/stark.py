from stark.service.v1 import site,StarkHandler
from web import models


class SchoolHandler(StarkHandler):
    list_display = ['title']


site.register(models.School)
