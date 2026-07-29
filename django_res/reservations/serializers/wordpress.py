"""Serializer for the WordPress-posted enquiry payload.

Field inventory = the REAL wire shape recovered from `ResSystem/vc_wp_1.sql`
(201 stored submissions: `Properties`/`RegionIds` string ids with "0"
sentinels, string-typed ints, UI-label `EnquireDateTypeString`, `CountryIds`
CSV, `UserFeedback`/`other_text`) unioned with the .NET DTO + Postman-sample
variants (`PropertyId`/`EnquireDateType` ints, `CountryId`, `Countries`,
`Regions`). ASP.NET silently dropped unknown keys, so undeclared keys are
ignored rather than rejected. Everything is optional and free-text caps are
generous — the service truncates to model widths; the intake never rejects a
lead over field length.
"""

from __future__ import annotations

from rest_framework import serializers


class WordPressEnquirySerializer(serializers.Serializer):
    FirstName = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    LastName = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    # CharField, not EmailField: a malformed address is still a lead to chase.
    Email = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    CountryCode = serializers.CharField(required=False, allow_blank=True, max_length=64)
    ContactNo = serializers.CharField(required=False, allow_blank=True, max_length=1024)

    PropertyId = serializers.IntegerField(required=False, allow_null=True)
    Properties = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    CountryId = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    CountryIds = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    Countries = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    Regions = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    # allow_null: the contact + wishlist forms have no RegionIds input, and the
    # theme's ajax handler wraps the missing key into array(null) on the wire.
    RegionIds = serializers.ListField(
        child=serializers.IntegerField(allow_null=True), required=False, allow_empty=True
    )

    EnquireDateType = serializers.IntegerField(required=False, allow_null=True)
    EnquireDateTypeString = serializers.CharField(required=False, allow_blank=True, max_length=255)
    FromDate = serializers.DateField(required=False, allow_null=True)
    ToDate = serializers.DateField(required=False, allow_null=True)

    MinBed = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    MaxBed = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    Adults = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    Children = serializers.IntegerField(required=False, allow_null=True, min_value=0)

    Notes = serializers.CharField(required=False, allow_blank=True)
    RequestType = serializers.CharField(required=False, allow_blank=True, max_length=255)
    referral = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    UserFeedback = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    other_text = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    IsSignUp = serializers.BooleanField(required=False, default=False)
