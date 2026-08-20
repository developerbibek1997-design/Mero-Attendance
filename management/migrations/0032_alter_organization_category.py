from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("management", "0031_organization_feature_notices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organization",
            name="category",
            field=models.CharField(
                choices=[
                    ("school", "School"),
                    ("college", "College"),
                    ("bachelor", "Bachelor"),
                    ("institute", "Institute/Consultancy"),
                    ("office", "Office"),
                    ("industry", "Industry"),
                    ("others", "Others"),
                ],
                default="others",
                max_length=50,
            ),
        ),
    ]
