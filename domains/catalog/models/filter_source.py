from django.db import models


class FilterSource(models.Model):
    name = models.CharField(max_length=100, unique=True)
    model_name = models.CharField(max_length=100)