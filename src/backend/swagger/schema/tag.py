from schematics.models import Model
from schematics.types import StringType, ModelType
from .external_documentation import ExternalDocumentation


class Tag(Model):
    """Allows adding meta data to a single tag that is used by the Operation Object. It is not mandatory to have a Tag Object per tag used there."""

    name = StringType(required=True)  # The name of the tag.
    description = StringType(serialize_when_none=False)  # A short description for the tag. GFM syntax can be used for rich text representation.
    externalDocs = ModelType(ExternalDocumentation, serialize_when_none=False)  # Additional external documentation for this tag.
