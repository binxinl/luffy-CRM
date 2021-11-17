from django.db import models

# Create your models here.

class School(models.Model):
    title = models.CharField(verbose_name='校区名称',max_length=32)

    def __str__(self):
        return self.title