# Data migration: legacy garment_template aliases → canonical keys.

from django.db import migrations

# Keep in sync with apps.designs.garment_choices.GARMENT_TEMPLATE_ALIASES
GARMENT_TEMPLATE_ALIASES = {
    "t-shirt": "tee",
    "tshirt": "tee",
    "t shirt": "tee",
    "polo-shirt": "polo",
    "poloshirt": "polo",
    "sweatshirt": "hoodie",
    "hooded": "hoodie",
}


def forwards(apps, schema_editor):
    Design = apps.get_model("designs", "Design")
    for old, new in GARMENT_TEMPLATE_ALIASES.items():
        Design.objects.filter(garment_template=old).update(garment_template=new)


def backwards(apps, schema_editor):
    # Aliases collapse many→one; cannot restore original legacy keys.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("designs", "0004_garment_choices"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
