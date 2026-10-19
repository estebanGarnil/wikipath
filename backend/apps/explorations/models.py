import uuid

from django.conf import settings
from django.db import models


class Exploration(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="explorations",
    )

    start_page_id = models.PositiveBigIntegerField()
    start_page_title = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["user", "-created_at", "-id"],
                name="exploration_user_created_idx",
            ),
        ]

    def __str__(self):
        return self.start_page_title


class ExplorationVisit(models.Model):
    exploration = models.ForeignKey(
        Exploration,
        on_delete=models.CASCADE,
        related_name="visits",
    )

    position = models.PositiveIntegerField()
    page_id = models.PositiveBigIntegerField()
    page_title = models.TextField()
    visited_at = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["exploration", "position"],
                name="unique_exploration_position",
            ),
        ]

    def __str__(self):
        return f"{self.position} - {self.page_title}"
