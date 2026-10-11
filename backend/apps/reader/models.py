from django.db import models


class ArticleRender(models.Model):
    article = models.OneToOneField('articles.Article', on_delete=models.CASCADE, primary_key=True)
    fingerprint = models.CharField(max_length=64)
    html = models.TextField()
    rendered_at = models.DateTimeField(auto_now=True)
