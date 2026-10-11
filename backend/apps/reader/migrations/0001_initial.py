import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [('articles', '0001_initial')]
    operations = [migrations.CreateModel(
        name='ArticleRender',
        fields=[
            ('article', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to='articles.article')),
            ('fingerprint', models.CharField(max_length=64)),
            ('html', models.TextField()),
            ('rendered_at', models.DateTimeField(auto_now=True)),
        ],
    )]
