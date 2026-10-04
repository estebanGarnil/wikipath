from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("articles", "0003_article_title_search"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="article",
            index=GinIndex(
                fields=["title_search"],
                name="article_title_search_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ),
    ]