# pylint: skip-file
import argparse
import codecs
import os


def generate_rst_files(package_root_path, doc_root_path):
    py_files = _get_py_files(package_root_path)
    api_rst_file_path = os.path.join(doc_root_path, "source", "api.rst")
    with codecs.open(api_rst_file_path, "w", encoding="utf-8") as api_rst_file:
        pkg_name = os.path.basename(package_root_path)
        api_rst_file.write(f"{pkg_name}\n")
        api_rst_file.write("=" * len(pkg_name) + "\n\n")
        if os.path.join(package_root_path, "__init__.py") in py_files:
            api_rst_file.write(f".. automodapi:: {pkg_name}.__init__\n")
            api_rst_file.write("   :no-inheritance-diagram:\n\n")
            api_rst_file.write("   :include-all-objects:\n\n")
        if os.path.join(package_root_path, "__main__.py") in py_files:
            api_rst_file.write(f".. automodapi:: {pkg_name}.__main__\n")
            api_rst_file.write("   :no-inheritance-diagram:\n\n")
            api_rst_file.write("   :include-all-objects:\n\n")
        if os.path.join(package_root_path, "main.py") in py_files:
            api_rst_file.write(f".. automodapi:: {pkg_name}.main\n")
            api_rst_file.write("   :no-inheritance-diagram:\n\n")
            api_rst_file.write("   :include-all-objects:\n\n")
        api_rst_file.write(f"{pkg_name} Submodules\n")
        api_rst_file.write("-" * len(f"{pkg_name} Submodules") + "\n\n")
        for py_file in py_files:
            module_name = _get_module_name(package_root_path, py_file)
            if module_name.startswith("_") or module_name == "main":
                continue
            rst_filename = f"{module_name}.rst"
            rst_path = os.path.join(doc_root_path, "source", rst_filename)
            with codecs.open(rst_path, "w", encoding="utf-8") as rst_file:
                rst_file.write(f"{module_name}\n")
                rst_file.write("=" * len(module_name) + "\n\n")
                rst_file.write(f".. automodapi:: {pkg_name}.{module_name}\n")
                rst_file.write("   :no-inheritance-diagram:\n")
                rst_file.write("   :include-all-objects:\n")
            api_rst_file.write(".. toctree::\n")
            api_rst_file.write("   :maxdepth: 1\n\n")
            api_rst_file.write(f"   {module_name}\n\n")


def _get_py_files(package_root_path):
    py_files = []
    for root, _, files in os.walk(package_root_path):
        for item in files:
            if item.endswith(".py"):
                py_files.append(os.path.join(root, item))
    return py_files


def _get_module_name(package_root_path, py_file):
    relative_path = os.path.relpath(py_file, package_root_path)
    module_name, _ = os.path.splitext(relative_path)
    return module_name.replace(os.sep, ".")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate .rst files for automodapi")
    parser.add_argument("src_root_path", help="Path to the package src folder")
    parser.add_argument("doc_root_path", help="Path to the docs folder")
    args = parser.parse_args()
    generate_rst_files(args.src_root_path, args.doc_root_path)
