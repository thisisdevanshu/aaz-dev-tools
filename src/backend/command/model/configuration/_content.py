from schematics.models import Model
from schematics.types import PolyModelType

from ._arg_builder import CMDArgBuilder
from ._fields import CMDVariantField
from ._schema import CMDSchemaBase, CMDSchema


# json
class CMDJson(Model):
    # properties as tags
    var = CMDVariantField(serialize_when_none=False)
    ref = CMDVariantField(serialize_when_none=False)

    # properties as nodes
    schema = PolyModelType(CMDSchemaBase, allow_subclasses=True)  # this property is required when ref property is None
    # Note: the schema can be CMDSchema or CMDSchemaBase.
    # For request or instance update, it's CMDSchema.
    # For response, it's CMDSchemaBase.

    def generate_args(self):
        if not self.schema:
            return []
        assert isinstance(self.schema, CMDSchema)
        builder = CMDArgBuilder.new_builder(schema=self.schema)
        args = builder.get_args()
        return args
