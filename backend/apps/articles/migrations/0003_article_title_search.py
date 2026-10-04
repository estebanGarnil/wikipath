from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("articles", "0002_enable_title_search"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="title_search",
            field=models.TextField(
                null=True,
                editable=False,
            ),
        ),
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION articles_set_title_search()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    NEW.title_search := lower(unaccent(NEW.title));
                    RETURN NEW;
                END;
                $$;

                CREATE TRIGGER articles_title_search_trigger
                BEFORE INSERT OR UPDATE OF title, title_search
                ON articles_article
                FOR EACH ROW
                EXECUTE FUNCTION articles_set_title_search();
            """,
            reverse_sql="""
                DROP TRIGGER articles_title_search_trigger
                ON articles_article;

                DROP FUNCTION articles_set_title_search();
            """,
        ),
    ]