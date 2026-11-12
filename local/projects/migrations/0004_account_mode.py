from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0003_sso_hosts"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="account_role",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AlterField(
            model_name="project",
            name="mode",
            field=models.CharField(
                choices=[
                    ("code", "Kod + sayt linki"),
                    ("code_admin", "Kod + sayt linki + admin login"),
                    ("admin", "Sayt linki + admin login (kodsiz)"),
                    ("account", "Sayt linki + bitta rolning login va paroli"),
                ],
                default="code",
                max_length=12,
            ),
        ),
    ]
