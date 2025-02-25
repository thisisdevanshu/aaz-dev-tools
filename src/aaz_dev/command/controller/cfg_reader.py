import json

from command.model.configuration import CMDConfiguration, CMDHttpOperation, CMDInstanceUpdateOperation, \
    CMDCommandGroup, CMDArgGroup, CMDObjectArg, CMDArrayArg, CMDObjectArgBase, CMDArrayArgBase


class CfgReader:

    def __init__(self, cfg):
        assert isinstance(cfg, CMDConfiguration)
        self.cfg = cfg

    @property
    def resources(self):
        return self.cfg.resources

    def iter_cfg_files_data(self):
        main_resource = self.cfg.resources[0]
        data = json.dumps(self.cfg.to_primitive(), ensure_ascii=False)
        yield main_resource.id, data
        for resource in self.cfg.resources[1:]:
            assert resource.version == main_resource.version
            data = json.dumps({"$ref": main_resource.id}, ensure_ascii=False)
            yield resource.id, data

    def iter_commands(self):
        groups = []
        for group in self.cfg.command_groups:
            groups.append((group.name.split(" "), group))
        idx = 0
        while idx < len(groups):
            node_names, command_group = groups[idx]
            assert isinstance(command_group, CMDCommandGroup)
            if command_group.commands:
                for command in command_group.commands:
                    yield [*node_names, command.name], command
            if command_group.command_groups:
                for group in command_group.command_groups:
                    groups.append(([*node_names, group.name], group))
            idx += 1

    def iter_commands_by_resource(self, resource_id, version=None):
        for cmd_name, command in self.iter_commands():
            for r in command.resources:
                if r.id == resource_id and (not version or r.version == version):
                    yield cmd_name, command
                    break

    def iter_commands_by_operations(self, *methods):
        # use 'update' as the methods of instance update operation
        methods = {m.lower() for m in methods}
        for cmd_names, command in self.iter_commands():
            ops_methods = set()
            has_extra_methods = False
            for operation in command.operations:
                if isinstance(operation, CMDInstanceUpdateOperation):
                    if 'update' not in methods:
                        has_extra_methods = True
                        break
                    ops_methods.add('update')
                elif isinstance(operation, CMDHttpOperation):
                    http = operation.http
                    if http.request.method.lower() not in methods:
                        has_extra_methods = True
                        break
                    ops_methods.add(http.request.method.lower())
            if not has_extra_methods and ops_methods == methods:
                yield cmd_names, command

    def find_command_group(self, *cg_names, parent=None):
        parent = parent or self.cfg
        if not cg_names:
            return None, None, parent, []
        cg_names = [*cg_names]

        group = None
        names = None
        if parent.command_groups:
            for sub_group in parent.command_groups:
                sub_names = sub_group.name.split(" ")
                if len(sub_names) < len(cg_names) and sub_names == cg_names[:len(sub_names)] or \
                        len(sub_names) >= len(cg_names) and sub_names[:len(cg_names)] == cg_names:
                    assert group is None and names is None, "multiple match found"
                    group = sub_group
                    names = sub_names

        if not group:
            return None, None, parent, cg_names

        if len(names) >= len(cg_names):
            tail_names = names[len(cg_names):]
            return group, tail_names, parent, cg_names

        return self.find_command_group(*cg_names[len(names):], parent=group)

    def find_command(self, *cmd_names):
        if len(cmd_names) < 2:
            return None
        cmd_names = [*cmd_names]

        command_group, tail_names, _, _ = self.find_command_group(*cmd_names[:-1])
        if command_group is None or tail_names:
            # group is not match cmd_names[:-1]
            return None
        name = cmd_names[-1]
        if command_group.commands:
            for command in command_group.commands:
                if command.name == name:
                    return command
        return None

    # command specific

    def find_arg(self, *cmd_names, idx):
        command = self.find_command(*cmd_names)
        if not command:
            return None

        if isinstance(idx, str):
            idx = self.arg_idx_to_list(idx)
        assert isinstance(idx, list), f"invalid arg_idx type: {type(idx)}"

        for arg_group in command.arg_groups:
            arg = self.find_arg_in_group(arg_group, idx)
            if arg:
                return arg

        return None

    def find_arg_parent(self, *cmd_names, idx):
        command = self.find_command(*cmd_names)
        if not command:
            return None, None

        if isinstance(idx, str):
            idx = self.arg_idx_to_list(idx)
        assert isinstance(idx, list), f"invalid arg_idx type: {type(idx)}"

        if len(idx) == 1:
            for arg_group in command.arg_groups:
                if self.find_arg_in_group(arg_group, idx) is not None:
                    return None, arg_group
        else:
            parent_idx = idx[:-1]
            parent_arg = self.find_arg(*cmd_names, idx=parent_idx)
            if parent_arg is not None:
                return parent_idx, parent_arg
        return None, None

    def find_arg_in_group(self, arg_group, idx):
        assert isinstance(arg_group, CMDArgGroup)

        if isinstance(idx, str):
            idx = self.arg_idx_to_list(idx)
        assert isinstance(idx, list) and len(idx) > 0

        current_idx = idx[0]
        remain_idx = idx[1:]
        for arg in arg_group.args:
            if current_idx in arg.options:
                if not remain_idx:
                    return arg
                return self.find_sub_arg(arg, remain_idx)
        return None

    def find_sub_arg(self, arg, idx):
        if isinstance(idx, str):
            idx = self.arg_idx_to_list(idx)
        assert isinstance(idx, list) and len(idx) > 0

        if isinstance(arg, CMDObjectArgBase):
            current_idx = idx[0]
            remain_idx = idx[1:]
            if current_idx == '{}':
                if arg.additional_props and arg.additional_props.item:
                    item = arg.additional_props.item
                    if not remain_idx:
                        return item
                    return self.find_sub_arg(item, remain_idx)
            elif arg.args:
                for sub_arg in arg.args:
                    if current_idx in sub_arg.options:
                        if not remain_idx:
                            return sub_arg
                        return self.find_sub_arg(sub_arg, remain_idx)

        elif isinstance(arg, CMDArrayArgBase):
            current_idx = idx[0]
            remain_idx = idx[1:]
            if current_idx == '[]':
                item = arg.item
                if not remain_idx:
                    return item
                return self.find_sub_arg(item, remain_idx)

        return None

    def find_arg_by_var(self, *cmd_names, arg_var):
        _, arg, arg_idx = self.find_arg_with_parent_by_var(*cmd_names, arg_var=arg_var)
        return arg, arg_idx

    def find_arg_with_parent_by_var(self, *cmd_names, arg_var):
        """
        :return: (parent, arg_idx, arg)
            parent: argument or arg_group
            arg_idx: argument idx in string
            arg: matched argument

            if argument is not flatten, return parent, arg_idx, arg
            else if argument is flatten, return parent, None, None
            else if argument is not exist, return None, None, None

        """
        command = self.find_command(*cmd_names)
        if not command:
            return None, None, None
        assert isinstance(arg_var, str), f"invalid arg_var type: {type(arg_var)}"

        def arg_filter(_parent, _arg, _arg_idx, _arg_var):
            if arg_var == _arg_var:
                # find match
                return (_parent, _arg, _arg_idx), True
            elif _arg_var.startswith(f'{arg_var}.'):
                # arg_var already been flattened
                return (_parent, None, None), True
            return None, False

        for arg_group in command.arg_groups:
            matches = [match for match in self._iter_args_in_group(
                arg_group, arg_filter=arg_filter
            )]
            if not matches:
                continue
            assert len(matches) == 1

            parent, arg, arg_idx = matches[0]
            if arg_idx:
                arg_idx = self.arg_idx_to_str(arg_idx)
            return parent, arg, arg_idx
        return None, None, None

    @classmethod
    def is_similar_args(cls, arg1, arg2):
        if set(arg1.options) != set(arg2.options):
            return False
        if arg1.stage != arg2.stage:
            return False
        if arg1.hide != arg2.hide:
            return False

        return cls._is_similar_args_in_base(arg1, arg2)

    @classmethod
    def _is_similar_args_in_base(cls, arg1, arg2):
        if isinstance(arg1, CMDArrayArgBase) and isinstance(arg2, CMDArrayArgBase):
            return cls._is_similar_args_in_base(arg1.item, arg2.item)
        elif isinstance(arg1, CMDObjectArgBase) and isinstance(arg2, CMDObjectArgBase):
            # verify args
            if (not arg1.args) != (not arg2.args):
                return False
            if arg1.args:
                if len(arg1.args) != len(arg2.args):
                    return False
                for sub_arg1 in arg1.args:
                    find_match = False
                    for sub_arg2 in arg2.args:
                        if cls.is_similar_args(sub_arg1, sub_arg2):
                            find_match = True
                            break
                    if not find_match:
                        return False

            # verify additional props
            if (arg1.additional_props is not None) != (arg2.additional_props is not None):
                return False
            if arg1.additional_props:
                if (arg1.additional_props.item is not None) != (arg2.additional_props.item is not None):
                    return False
                if arg1.additional_props.item:
                    if not cls._is_similar_args_in_base(arg1.additional_props.item, arg2.additional_props.item):
                        return False
        elif arg1.type != arg2.type:
            # handle cls argument
            if arg1.type.startswith("@") and arg1.type == getattr(arg2, 'cls', None):
                return True
            if arg2.type.startswith("@") and arg2.type == getattr(arg1, 'cls', None):
                return True
            return False
        return True

    def find_arg_cls_definition(self, *cmd_names, cls_name):
        command = self.find_command(*cmd_names)
        if not command:
            return None, None, None

        assert isinstance(cls_name, str) and not cls_name.startswith('@')

        def arg_filter(_parent, _arg, _arg_idx, _arg_var):
            if getattr(_arg, 'cls', None) == cls_name:
                # find match
                return (_parent, _arg, _arg_idx), True
            return None, False

        for arg_group in command.arg_groups:
            matches = [match for match in self._iter_args_in_group(
                arg_group, arg_filter=arg_filter
            )]
            if not matches:
                continue
            assert len(matches) == 1

            parent, arg, arg_idx = matches[0]
            if arg_idx:
                arg_idx = self.arg_idx_to_str(arg_idx)
            return parent, arg, arg_idx
        return None, None, None

    def iter_arg_cls_definition(self, *cmd_names, cls_name_prefix):
        command = self.find_command(*cmd_names)
        if not command:
            return

        assert isinstance(cls_name_prefix, str) and not cls_name_prefix.startswith('@')
        if not cls_name_prefix.endswith('_'):
            cls_name_prefix += '_'

        def arg_filter(_parent, _arg, _arg_idx, _arg_var):
            _cls = getattr(_arg, 'cls', None)
            if _cls is not None and _cls.startswith(cls_name_prefix):
                # find match
                return (_parent, _arg, _arg_idx), False
            return None, False

        for arg_group in command.arg_groups:
            for parent, arg, arg_idx in self._iter_args_in_group(arg_group, arg_filter=arg_filter):
                if arg_idx:
                    arg_idx = self.arg_idx_to_str(arg_idx)
                yield parent, arg, arg_idx

    def iter_arg_cls_reference(self, *cmd_names, cls_name):
        command = self.find_command(*cmd_names)
        if not command:
            return

        assert isinstance(cls_name, str) and not cls_name.startswith('@')

        cls_type_name = f"@{cls_name}"

        def arg_filter(_parent, _arg, _arg_idx, _arg_var):
            if _arg.type == cls_type_name:
                # find match
                return (_parent, _arg, _arg_idx), False
            return None, False

        for arg_group in command.arg_groups:
            for parent, arg, arg_idx in self._iter_args_in_group(
                    arg_group, arg_filter=arg_filter):
                if arg_idx:
                    arg_idx = self.arg_idx_to_str(arg_idx)
                yield parent, arg, arg_idx

    def _iter_args_in_group(self, arg_group, arg_filter):
        assert isinstance(arg_group, CMDArgGroup)
        for arg in arg_group.args:
            arg_option = max(arg.options, key=lambda item: len(item))
            match, ret = arg_filter(arg_group, arg, [arg_option], arg.var)
            if match:
                yield match
            if ret:
                return

            if isinstance(arg, (CMDObjectArg, CMDArrayArg)):
                for sub_parent, sub_arg, sub_arg_idx in self._iter_sub_args(arg, arg.var, arg_filter):
                    if sub_arg_idx:
                        sub_arg_idx = [arg_option, *sub_arg_idx]
                    yield sub_parent, sub_arg, sub_arg_idx

    def _iter_sub_args(self, parent, arg_var, arg_filter):
        if isinstance(parent, CMDObjectArgBase):
            if parent.args:
                for arg in parent.args:
                    arg_option = max(arg.options, key=lambda item: len(item))
                    match, ret = arg_filter(parent, arg, [arg_option], arg.var)
                    if match:
                        yield match
                    if ret:
                        return

                    if isinstance(arg, (CMDObjectArg, CMDArrayArg)):
                        for sub_parent, sub_arg, sub_arg_idx in self._iter_sub_args(arg, arg.var, arg_filter):
                            if sub_arg:
                                sub_arg_idx = [arg_option, *sub_arg_idx]
                            yield sub_parent, sub_arg, sub_arg_idx

            if parent.additional_props and parent.additional_props.item:
                item = parent.additional_props.item
                item_var = arg_var + "{}"

                match, ret = arg_filter(parent, item, ["{}"], item_var)
                if match:
                    yield match
                if ret:
                    return

                for sub_parent, sub_arg, sub_arg_idx in self._iter_sub_args(item, item_var, arg_filter):
                    if sub_arg:
                        sub_arg_idx = ['{}', *sub_arg_idx]
                    yield sub_parent, sub_arg, sub_arg_idx

        elif isinstance(parent, CMDArrayArgBase):
            item = parent.item
            item_var = arg_var + '[]'

            match, ret = arg_filter(parent, item, ["[]"], item_var)
            if match:
                yield match
            if ret:
                return

            for sub_parent, sub_arg, sub_arg_idx in self._iter_sub_args(item, item_var, arg_filter):
                if sub_arg:
                    sub_arg_idx = ['[]', *sub_arg_idx]
                yield sub_parent, sub_arg, sub_arg_idx

    @staticmethod
    def arg_idx_to_list(arg_idx):
        if isinstance(arg_idx, list):
            return arg_idx
        assert isinstance(arg_idx, str)
        arg_idx = arg_idx.replace('{}', '.{}').replace('[]', '.[]').split('.')
        return [idx for idx in arg_idx if idx]

    @staticmethod
    def arg_idx_to_str(arg_idx):
        if isinstance(arg_idx, str):
            return arg_idx
        assert isinstance(arg_idx, list)
        return '.'.join(arg_idx).replace('.{}', '{}').replace('.[]', '[]')
