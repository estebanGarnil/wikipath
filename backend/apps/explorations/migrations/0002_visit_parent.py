import django.db.models.deletion
from django.db import migrations, models


def link_existing_visits(apps, schema_editor):
    Visit = apps.get_model("explorations", "ExplorationVisit")
    database = schema_editor.connection.alias

    visits = (
        Visit.objects.using(database)
        .only("id", "exploration_id", "position", "parent")
        .order_by("exploration_id", "position", "id")
    )

    previous_exploration = None
    previous_visit_id = None
    pending = []

    for visit in visits.iterator(chunk_size=1000):
        if visit.exploration_id != previous_exploration:
            previous_exploration = visit.exploration_id
            previous_visit_id = None

        visit.parent_id = previous_visit_id
        pending.append(visit)
        previous_visit_id = visit.pk

        if len(pending) >= 1000:
            Visit.objects.using(database).bulk_update(
                pending,
                ["parent"],
                batch_size=1000,
            )
            pending = []

    if pending:
        Visit.objects.using(database).bulk_update(
            pending,
            ["parent"],
            batch_size=1000,
        )


def unlink_existing_visits(apps, schema_editor):
    Visit = apps.get_model("explorations", "ExplorationVisit")
    Visit.objects.using(schema_editor.connection.alias).update(
        parent_id=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("explorations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="explorationvisit",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="explorations.explorationvisit",
            ),
        ),
        migrations.RunPython(
            link_existing_visits,
            reverse_code=unlink_existing_visits,
        ),
    ]