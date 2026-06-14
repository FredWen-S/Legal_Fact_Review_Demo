from __future__ import annotations


class UserFacingError(Exception):
    """Exception whose message can be shown directly in the Streamlit UI."""


class UnsupportedFileTypeError(UserFacingError):
    pass


class EmptyFileError(UserFacingError):
    pass


class ParseError(UserFacingError):
    pass


class ExcelSchemaError(UserFacingError):
    pass


class OcrDependencyError(UserFacingError):
    pass
