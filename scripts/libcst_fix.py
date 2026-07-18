import libcst as cst
from libcst import matchers as m
from typing import Optional
import os
import glob
from pathlib import Path

class TypingFixer(cst.CSTTransformer):
    def __init__(self):
        self.needs_any = False

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
        new_params = []
        for param in updated_node.params.params:
            if param.annotation is None and param.name.value not in ('self', 'cls'):
                self.needs_any = True
                new_param = param.with_changes(
                    annotation=cst.Annotation(annotation=cst.Name("Any"))
                )
                new_params.append(new_param)
            else:
                new_params.append(param)
                
        new_kwonly = []
        for param in updated_node.params.kwonly_params:
            if param.annotation is None:
                self.needs_any = True
                new_param = param.with_changes(
                    annotation=cst.Annotation(annotation=cst.Name("Any"))
                )
                new_kwonly.append(new_param)
            else:
                new_kwonly.append(param)
                
        # Star arg (*args)
        new_star_arg = updated_node.params.star_arg
        if isinstance(new_star_arg, cst.Param) and new_star_arg.annotation is None:
            self.needs_any = True
            new_star_arg = new_star_arg.with_changes(annotation=cst.Annotation(annotation=cst.Name("Any")))
            
        # Kwarg (**kwargs)
        new_kwarg = updated_node.params.star_kwarg
        if isinstance(new_kwarg, cst.Param) and new_kwarg.annotation is None:
            self.needs_any = True
            new_kwarg = new_kwarg.with_changes(annotation=cst.Annotation(annotation=cst.Name("Any")))

        new_params_node = updated_node.params.with_changes(
            params=new_params,
            kwonly_params=new_kwonly,
            star_arg=new_star_arg,
            star_kwarg=new_kwarg
        )

        new_returns = updated_node.returns
        if original_node.name.value in ('__init__', 'handle', 'ready'):
            if new_returns is None or getattr(new_returns.annotation, 'value', None) != 'None':
                new_returns = cst.Annotation(annotation=cst.Name("None"))
        else:
            if new_returns is None:
                self.needs_any = True
                new_returns = cst.Annotation(annotation=cst.Name("Any"))

        return updated_node.with_changes(params=new_params_node, returns=new_returns)

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        if self.needs_any:
            has_any_import = False
            for stmt in updated_node.body:
                if m.matches(stmt, m.SimpleStatementLine(body=[m.ImportFrom(module=m.Name("typing"))])):
                    for import_stmt in stmt.body:
                        if isinstance(import_stmt, cst.ImportFrom) and getattr(import_stmt.module, 'value', '') == 'typing':
                            names = getattr(import_stmt, 'names', [])
                            if isinstance(names, cst.ImportAlias) and names.name.value == 'Any':
                                has_any_import = True
                            elif isinstance(names, list) or isinstance(names, tuple):
                                for name in names:
                                    if getattr(name.name, 'value', '') == 'Any':
                                        has_any_import = True

            if not has_any_import:
                import_stmt = cst.SimpleStatementLine(
                    body=[
                        cst.ImportFrom(
                            module=cst.Name("typing"),
                            names=[cst.ImportAlias(name=cst.Name("Any"))]
                        )
                    ]
                )
                
                insert_idx = 0
                for i, stmt in enumerate(updated_node.body):
                    if m.matches(stmt, m.SimpleStatementLine(body=[m.ImportFrom(module=m.Name("__future__"))])):
                        insert_idx = i + 1
                    elif isinstance(stmt, cst.SimpleStatementLine) and isinstance(stmt.body[0], cst.Expr) and isinstance(getattr(stmt.body[0], 'value', None), cst.SimpleString) and i == 0:
                        insert_idx = i + 1
                        
                new_body = list(updated_node.body)
                new_body.insert(insert_idx, import_stmt)
                return updated_node.with_changes(body=new_body)
                
        return updated_node

def process_file(filepath):
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        
        module = cst.parse_module(source)
        fixer = TypingFixer()
        modified_module = module.visit(fixer)
        
        if fixer.needs_any or source != modified_module.code:
            with open(filepath, 'w') as f:
                f.write(modified_module.code)
            print(f"Fixed {filepath}")
    except Exception as e:
        print(f"Failed to process {filepath}: {e}")

if __name__ == "__main__":
    for filepath in glob.glob('micboard/**/*.py', recursive=True):
        if 'migrations' not in filepath:
            process_file(filepath)
