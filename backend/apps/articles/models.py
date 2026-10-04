import zlib

from django.db import models
from django.contrib.postgres.indexes import GinIndex


class Article(models.Model):
    page_id = models.BigIntegerField(primary_key=True)
    title = models.TextField()
    title_search = models.TextField(
        null=True,
        editable=False,
    )
    revision_id = models.BigIntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    wikitext_zlib = models.BinaryField()

    @property
    def wikitext(self):
        return zlib.decompress(bytes(self.wikitext_zlib)).decode("utf-8")

    def __str__(self):
        return self.title

    class Meta:
        indexes = [
            GinIndex(
                fields=["title_search"],
                name="article_title_search_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ]