from tortoise import fields, models


class User(models.Model):
    id = fields.IntField(primary_key=True)
    username = fields.CharField(max_length=12)
    username_lower = fields.CharField(max_length=12, unique=True)
    display_name = fields.CharField(max_length=12, unique=True)
    avatar_url = fields.CharField(max_length=512, null=True)
    password_hash = fields.CharField(max_length=255, null=True)
    email = fields.CharField(max_length=254, unique=True, null=True)
    email_verified_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    async def save(self, *args, **kwargs):
        self.username_lower = self.username.lower()
        if self.email:
            self.email = self.email.strip().lower()
        return await super().save(*args, **kwargs)


class Conversation(models.Model):
    id = fields.IntField(primary_key=True)
    user_a = fields.ForeignKeyField("models.User", related_name="conversations_a", on_delete=fields.CASCADE)
    user_b = fields.ForeignKeyField("models.User", related_name="conversations_b", on_delete=fields.CASCADE)
    ttl_seconds = fields.IntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = (("user_a", "user_b"),)

    async def save(self, *args, **kwargs):
        if self.user_a_id == self.user_b_id:
            raise ValueError("A conversation requires two different users")
        if self.user_a_id > self.user_b_id:
            self.user_a_id, self.user_b_id = self.user_b_id, self.user_a_id
        return await super().save(*args, **kwargs)
