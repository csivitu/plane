# Python imports
import traceback
import uuid
import zoneinfo

# Django imports
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError
from django.urls import resolve
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend

# Third part imports
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

# Module imports
from plane.authentication.session import BaseSessionAuthentication
from plane.utils.exception_logger import log_exception
from plane.utils.paginator import BasePaginator
from plane.db.models import ProjectIdentifier


class TimezoneMixin:
    """
    This enables timezone conversion according
    to the user set timezone
    """

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.user.is_authenticated:
            timezone.activate(zoneinfo.ZoneInfo(request.user.user_timezone))
        else:
            timezone.deactivate()


class BaseViewSet(TimezoneMixin, ModelViewSet, BasePaginator):
    model = None

    permission_classes = [
        IsAuthenticated,
    ]

    filter_backends = (
        DjangoFilterBackend,
        SearchFilter,
    )

    authentication_classes = [
        BaseSessionAuthentication,
    ]

    filterset_fields = []

    search_fields = []

    def is_uuid(self, value):
        try:
            # Check if the value is a valid UUID
            uuid.UUID(str(value))
            return True
        except ValueError:
            return False

    def get_project_id(self, project_id):
        # If the project_id is present and is not a UUID then get the project_id from the project_identifier
        if project_id and not self.is_uuid(project_id):
            project_identifier = (
                ProjectIdentifier.objects.filter(
                    workspace__slug=self.workspace_slug, name=project_id
                )
                .values("project_id")
                .first()
            )
            # If the project_identifier is not present then raise ObjectDoesNotExist
            if not project_identifier:
                raise ObjectDoesNotExist

            # Update the project_id in the kwargs
            return project_identifier.get("project_id")
        return project_id

    def get_issue_id(self, issue_id):
        # If the issue_id is present and is not a UUID then get the issue_id from the issue_identifier
        if issue_id and not self.is_uuid(issue_id):
            pass
        return issue_id

    def get_queryset(self):
        try:
            return self.model.objects.all()
        except Exception as e:
            log_exception(e)
            raise APIException(
                "Please check the view", status.HTTP_400_BAD_REQUEST
            )

    def handle_exception(self, exc):
        """
        Handle any exception that occurs, by returning an appropriate response,
        or re-raising the error.
        """
        try:
            response = super().handle_exception(exc)
            return response
        except Exception as e:
            (
                print(e, traceback.format_exc())
                if settings.DEBUG
                else print("Server Error")
            )
            if isinstance(e, IntegrityError):
                return Response(
                    {"error": "The payload is not valid"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if isinstance(e, ValidationError):
                return Response(
                    {"error": "Please provide valid detail"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if isinstance(e, ObjectDoesNotExist):
                return Response(
                    {"error": "The required object does not exist."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if isinstance(e, KeyError):
                log_exception(e)
                return Response(
                    {"error": "The required key does not exist."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            log_exception(e)
            return Response(
                {"error": "Something went wrong please try again later"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def dispatch(self, request, *args, **kwargs):
        try:
            # Write identifier to the uuid
            project_id = self.kwargs.get("project_id", None)
            if project_id:
                self.kwargs["project_id"] = self.get_project_id(project_id)
            # Check issue_id is present in the kwargs
            issue_id = self.kwargs.get("issue_id", None)
            if issue_id:
                self.kwargs["issue_id"] = self.get_issue_id(issue_id)
            # If the project_id is not present then get the project_id from the project_identifier
            response = super().dispatch(request, *args, **kwargs)

            # Print the number of queries if the debug is enabled
            if settings.DEBUG:
                from django.db import connection

                print(
                    f"{request.method} - {request.get_full_path()} of Queries: {len(connection.queries)}"
                )

            # Return the response
            return response
        except Exception as exc:
            response = self.handle_exception(exc)
            return exc

    @property
    def workspace_slug(self):
        return self.kwargs.get("slug", None)

    @property
    def project_id(self):
        project_id = self.kwargs.get("project_id", None)
        if project_id:
            return project_id

        if resolve(self.request.path_info).url_name == "project":
            return self.kwargs.get("pk", None)

    @property
    def fields(self):
        fields = [
            field
            for field in self.request.GET.get("fields", "").split(",")
            if field
        ]
        return fields if fields else None

    @property
    def expand(self):
        expand = [
            expand
            for expand in self.request.GET.get("expand", "").split(",")
            if expand
        ]
        return expand if expand else None


class BaseAPIView(TimezoneMixin, APIView, BasePaginator):
    permission_classes = [
        IsAuthenticated,
    ]

    filter_backends = (
        DjangoFilterBackend,
        SearchFilter,
    )

    authentication_classes = [
        BaseSessionAuthentication,
    ]

    filterset_fields = []

    search_fields = []

    def filter_queryset(self, queryset):
        for backend in list(self.filter_backends):
            queryset = backend().filter_queryset(self.request, queryset, self)
        return queryset

    def handle_exception(self, exc):
        """
        Handle any exception that occurs, by returning an appropriate response,
        or re-raising the error.
        """
        try:
            response = super().handle_exception(exc)
            return response
        except Exception as e:
            if isinstance(e, IntegrityError):
                return Response(
                    {"error": "The payload is not valid"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if isinstance(e, ValidationError):
                return Response(
                    {"error": "Please provide valid detail"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if isinstance(e, ObjectDoesNotExist):
                return Response(
                    {"error": "The required object does not exist."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if isinstance(e, KeyError):
                return Response(
                    {"error": "The required key does not exist."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            log_exception(e)
            return Response(
                {"error": "Something went wrong please try again later"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def dispatch(self, request, *args, **kwargs):
        try:
            response = super().dispatch(request, *args, **kwargs)

            if settings.DEBUG:
                from django.db import connection

                print(
                    f"{request.method} - {request.get_full_path()} of Queries: {len(connection.queries)}"
                )
            return response

        except Exception as exc:
            response = self.handle_exception(exc)
            return exc

    @property
    def workspace_slug(self):
        return self.kwargs.get("slug", None)

    @property
    def project_id(self):
        return self.kwargs.get("project_id", None)

    @property
    def fields(self):
        fields = [
            field
            for field in self.request.GET.get("fields", "").split(",")
            if field
        ]
        return fields if fields else None

    @property
    def expand(self):
        expand = [
            expand
            for expand in self.request.GET.get("expand", "").split(",")
            if expand
        ]
        return expand if expand else None
