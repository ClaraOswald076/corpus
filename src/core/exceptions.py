class PlatformError(Exception):
    pass


class AgentNotFoundError(PlatformError):
    pass


class DepartmentNotFoundError(PlatformError):
    pass


class TaskNotFoundError(PlatformError):
    pass


class MeetingNotFoundError(PlatformError):
    pass


class InvalidStateTransitionError(PlatformError):
    pass


class CircularDependencyError(PlatformError):
    pass


class EscalationLimitExceededError(PlatformError):
    pass


class MissingSecretariatError(PlatformError):
    pass


class MeetingStalemateError(PlatformError):
    pass


class AgentNotAvailableError(PlatformError):
    pass


class PermissionDeniedError(PlatformError):
    pass


class OrganizationConstraintError(PlatformError):
    pass


class RecruitmentError(PlatformError):
    pass
