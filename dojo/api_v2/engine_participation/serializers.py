from rest_framework import serializers


class DeleteHCParticipationRecordsRequestSerializer(serializers.Serializer):
    start_date = serializers.DateField(
        required=True,
        help_text="Start of the date range (inclusive), format YYYY-MM-DD.",
    )
    end_date = serializers.DateField(
        required=True,
        help_text="End of the date range (inclusive), format YYYY-MM-DD.",
    )


class ReturnHCParticipationToPendingRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional reason for returning the request to Pending.",
    )
