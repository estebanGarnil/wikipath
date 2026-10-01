import zlib

from django.db import models


class Article(models.Model):
    page_id = models.BigIntegerField(primary_key=True)
    title = models.TextField()
    revision_id = models.BigIntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    wikitext_zlib = models.BinaryField()

    @property
    def wikitext(self):
        return zlib.decompress(bytes(self.wikitext_zlib)).decode("utf-8")

    def __str__(self):
        return self.title