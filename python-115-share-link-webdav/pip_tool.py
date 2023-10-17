#!/usr/bin/env python3
# coding: utf-8

"""This module provides pip based tool functions."""

__author__  = "ChenyangGao <https://chenyanggao.github.io/>"
__version__ = (0, 0, 1)
__all__ = [
    "check_pip", "install_pip", "install_pip_by_ensurepip", "install_pip_by_getpip", 
    "pip_run", "pip_install", "pip_uninstall", "ensure_install", "ensure_uninstall", 
    "ensure_import", "iter_packages", "iter_uptodate_packages", "iter_outdated_packages", 
    "iter_latest_info", "update_all_packages", 
]

from importlib import import_module
from importlib.util import find_spec
from os import environ
from subprocess import run as sprun
from sys import executable
from tempfile import NamedTemporaryFile
from typing import cast, Final, Iterable, Iterator, NamedTuple, Optional, Sequence, Union
from types import ModuleType
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen


_PLATFORM_IS_WINDOWS: Final[bool] = __import__("platform").system() == "Windows"


def check_pip(ensure: bool = True) -> bool:
    """Check if the `pip` package is installed."""
    try:
        # Check whether the `pip` package can be imported
        import pip # type: ignore
    except ImportError:
        # If the `pip` package can't be imported, there may be reasons why it can't be installed
        try:
            ## Check configurations for `site-packages` 
            # USER_BASE: Path to the base directory for the user site-packages.
            # [site.USER_BASE](https://docs.python.org/3/library/site.html#site.USER_BASE)
            # USER_SITE: Path to the user site-packages for the running Python.
            # [site.USER_SITE](https://docs.python.org/3/library/site.html#site.USER_SITE)
            # NOTE: I found that the following file has a function `create_site_py`, `create_site_py` creates a site.py, 
            #       it is the actual imported `site` module in Windows platform, but there are lot of missing things: 
            # https://github.com/Sigil-Ebook/Sigil/blob/master/src/Resource_Files/python_pkg/windows_python_gather.py
            from site import USER_BASE, USER_SITE
            # TODO: I need to confirm whether the `site` built-in module exists in Windows platform, 
            #       if so, I can find out the values of `USER_BASE` and `USER_SITE` that are not missing, 
            #       otherwise, I may try to construct available values for `USER_BASE` and `USER_SITE`.
        except ImportError:
            print('''Defective Python executable detected.
Please replace current Python executable with another Python executable with `pip` package 
or replace with another Python executable which can install `pip` package 
(the `site` module defines available `USER_BASE` and `USER_SITE`).

Python official download address: https://www.python.org/downloads/

Tips: If you installed Python from source, with an installer from python.org, 
you should already have `pip`. If you installed using your OS package manager, 
`pip` may have been installed, or you can install separately by the same package manager.''')
            return False
        else:
            if not ensure:
                return False
            try:
                install_pip()
            except:
                return False
    return True


def install_pip(new_process: bool = True):
    """Install `pip` package.
    Reference:
        - https://docs.python.org/3/installing/index.html#pip-not-installed
    """
    try:
        install_pip_by_ensurepip("--default-pip", new_process=new_process)
    except:
        args: list[str] = []
        index_url = environ.get("PIP_INDEX_URL")
        trusted_host = environ.get("PIP_TRUSTED_HOST")
        if index_url:
            args.extend(("--index-url", index_url))
            if index_url.startswith("http://") and not trusted_host:
                trusted_host = urlparse(index_url).netloc
            if trusted_host:
                args.extend(("--trusted-host", trusted_host))
        install_pip_by_getpip(*args, new_process=new_process)


def install_pip_by_ensurepip(*args: str, new_process: bool = True):
    '''Install `pip` package using `ensurepip` package.
    Reference:
        - https://docs.python.org/3/library/ensurepip.html
        - https://packaging.python.org/tutorials/installing-packages/#ensure-you-can-run-pip-from-the-command-line
    '''
    if new_process:
        sprun([executable, "-m", "ensurepip", *args], check=True, shell=_PLATFORM_IS_WINDOWS)
    else:
        from ensurepip import _main # type: ignore
        _main(list(*args))


def install_pip_by_getpip(*args, new_process: bool = True):
    """Install `pip` package using "get-pip.py" script.
    Reference:
        - https://pip.pypa.io/en/stable/installation/
        - https://github.com/pypa/get-pip
        - https://bootstrap.pypa.io/get-pip.py
        - https://packaging.python.org/tutorials/installing-packages/#ensure-you-can-run-pip-from-the-command-line
    """
    url = "https://bootstrap.pypa.io/get-pip.py"
    context = __import__("ssl")._create_unverified_context()
    try:
        script = urlopen(url, context=context, timeout=3).read()
    except URLError:
        # For people who living in Chinese Mainland
        url = "https://ghproxy.com/https://raw.githubusercontent.com/pypa/get-pip/main/public/get-pip.py"
        script = urlopen(url, context=context, timeout=3).read()
    script = b"""\
#!/usr/bin/env python3
# coding: utf-8

import site as _site
from os import path as _path

if not hasattr(_site, "PREFIXES"):
    _site.PREFIXES = [__import__("sys").prefix, __import__("sys").exec_prefix]

_site.ENABLE_USER_SITE = True

_libpath = _path.dirname(_site.__file__)
if not hasattr(_site, "USER_BASE"):
    _site.USER_BASE = _path.dirname(_libpath)
if not hasattr(_site, "USER_SITE"):
    _site.USER_SITE = _path.join(_libpath, "site-packages")

del _site, _path, _libpath
""" + script
    if new_process:
        with NamedTemporaryFile(mode="wb", suffix=".py") as f:
            f.write(script)
            f.flush
            sprun([executable, f.name, *args], check=True, shell=_PLATFORM_IS_WINDOWS)
    else:
        import sys
        argv = sys.argv
        try:
            sys.argv = list(args)
            exec(script, {})
        finally:
            sys.argv = argv


check_pip()


from pip._internal.cli import base_command
from pip._internal.commands import create_command
from pip._internal.commands.list import ListCommand
from pip._internal.metadata import get_environment
from pip._internal.metadata.pkg_resources import BaseDistribution
from pip._internal.models.candidate import InstallationCandidate
from pip._internal.utils.compat import stdlib_pkgs
from pip._internal.utils.temp_dir import global_tempdir_manager, tempdir_registry
from pip._vendor.packaging.utils import canonicalize_name


def pip_run(
    command: str, 
    *args: str, 
    new_process: bool = True, 
):
    "Run the `pip` command with the same arguments as the command line."
    if new_process:
        sprun([executable, "-m", "pip", command, *args], 
              check=True, shell=_PLATFORM_IS_WINDOWS)
    else:
        cmd = create_command(command)
        args_ = list(args)
        options, args_ = cmd.parse_args(args_)
        base_command.setup_logging(
            verbosity     = options.verbose,
            no_color      = options.no_color,
            user_log_file = options.log,
        )
        with cmd.main_context():
            cmd.tempdir_registry = cmd.enter_context(tempdir_registry())
            cmd.enter_context(global_tempdir_manager())
            cmd.run(options, args_)


def pip_install(
    module: str, 
    /, 
    *modules: str, 
    upgrade: bool = False, 
    index_url: Optional[str] = None, 
    trusted_host: Optional[str] = None, 
    other_args: Iterable[str] = (), 
    new_process: bool = True, 
):
    """Use the `pip install` command with the same arguments as the command line.
    """
    args = ["install"]
    if upgrade:
        args.append("--upgrade")
    index_url = index_url or environ.get("PIP_INDEX_URL")
    trusted_host = trusted_host or environ.get("PIP_TRUESTED_HOST")
    if index_url:
        args.extend(("--index-url", index_url))
        if index_url.startswith("http://") and not trusted_host:
            trusted_host = urlparse(index_url).netloc
        if trusted_host:
            args.extend(("--trusted-host", trusted_host))
    return pip_run(*args, *other_args, module, *modules, new_process=new_process)


def pip_uninstall(
    module: str, 
    /, 
    *modules: str, 
    other_args: Iterable[str] = ('--yes',), 
    new_process: bool = False, 
):
    """Use the `pip uninstall` command with the same arguments as the command line.
    """
    return pip_run("uninstall", *other_args, module, *modules, new_process=new_process)


def module_exists(
    module: str, 
    not_actual_import: bool = True, 
) -> bool:
    """Test whether a module/package exists.

    :param module: The module is being tested for existence.
    :param not_actual_import: If false, perform an actual importing.
    """
    if not_actual_import:
        return find_spec(module) is not None
    else:
        try:
            import_module(module)
            return True
        except ModuleNotFoundError:
            return False


def ensure_install(
    module: str, 
    dependencies: Union[None, str, Sequence[str]] = None, 
    not_actual_import: bool = True, 
) -> None:
    """Ensure that a module is installed.

    :param module: The module is being tested for existence.
    :param dependencies: If the `module` does not exist, install these `dependencies`. 
        If the `dependencies` is None, install the `module` as `dependencies` directly.
    :param not_actual_import: If false, perform an actual importing.
    """
    if not module_exists(module, not_actual_import):
        if dependencies is None:
            pip_install(module)
        elif isinstance(dependencies, str):
            pip_install(dependencies)
        elif dependencies:
            pip_install(*dependencies)


def ensure_uninstall(
    module: str, 
    dependencies: Union[None, str, Sequence[str]] = None, 
    not_actual_import: bool = True, 
) -> None:
    """Ensure that a module is uninstalled.

    :param module: The module is being tested for existence.
    :param dependencies: If the `module` exists, uninstall these `dependencies`. 
        If the `dependencies` is None, uninstall the `module` as `dependencies` directly.
    :param not_actual_import: If false, perform an actual importing.
    """
    if module_exists(module, not_actual_import):
        if dependencies is None:
            pip_uninstall(module)
        elif isinstance(dependencies, str):
            pip_uninstall(dependencies)
        elif dependencies:
            pip_uninstall(*dependencies)


def ensure_import(
    module: str, 
    dependencies: Union[None, str, Sequence[str]] = None, 
) -> ModuleType:
    """Import the `module`, if it does not exist, try to install the `dependencies`, 
    and then import it again.

    :param module: The module is being tested for existence.
    :param dependencies: If the `module` does not exist, install these `dependencies`. 
        If the `dependencies` is None, install the `module` as `dependencies` directly.
    """
    try:
        return import_module(module)
    except ModuleNotFoundError:
        if dependencies is None:
            pip_install(module)
        elif isinstance(dependencies, str):
            pip_install(dependencies)
        elif dependencies:
            pip_install(*dependencies)
    return import_module(module)


def iter_packages(
    list_command_args: list[str] = [], 
    get_latest_version: bool = False, 
) -> Iterator[BaseDistribution]:
    """Iterate over the distribution info of all installed packages.
    """
    cmd = cast(ListCommand, create_command('list'))
    options, _ = cmd.parse_args(list_command_args)
    skip = set(stdlib_pkgs)
    if options.excludes:
        skip.update(map(canonicalize_name, options.excludes))
    packages = get_environment(options.path).iter_installed_distributions(
        local_only        = options.local,
        user_only         = options.user,
        editables_only    = options.editable,
        include_editables = options.include_editable,
        skip              = skip,
    )
    if get_latest_version:
        packages = cmd.iter_packages_latest_infos(packages, options) # type: ignore
    return packages


def iter_uptodate_packages(
    list_command_args: list[str] = [], 
) -> Iterator[BaseDistribution]:
    """Iterate over the distribution info of all installed and updated packages.
    """
    for dist in iter_packages(get_latest_version=True):
        if dist.version >= dist.latest_version: # type: ignore
            yield dist


def iter_outdated_packages(
    list_command_args: list[str] = [], 
) -> Iterator[BaseDistribution]:
    """Iterate over the distribution info of all installed but not updated packages.
    """
    for dist in iter_packages(get_latest_version=True):
        if dist.version < dist.latest_version: # type: ignore
            yield dist


class LatestInfo(NamedTuple):
    canonical_name: str
    latest_info: Optional[InstallationCandidate]


def iter_latest_info(
    canonical_names: Iterable[str], 
    list_command_args: list[str] = [], 
) -> Iterator[LatestInfo]:
    """Iterate over the latest info of all installed packages.
    """
    cmd = cast(ListCommand, create_command('list'))
    options, _ = cmd.parse_args(list_command_args)
    with cmd._build_session(options) as session:
        finder = cmd._build_package_finder(options, session)

        def latest_info(canonical_name):
            all_candidates = finder.find_all_candidates(canonical_name)
            if not options.pre:
                # Remove prereleases
                all_candidates = [
                    candidate
                    for candidate in all_candidates
                    if not candidate.version.is_prerelease
                ]
            evaluator = finder.make_candidate_evaluator(project_name=canonical_name)
            return evaluator.sort_best_candidate(all_candidates)

        for canonical_name in canonical_names:
            yield LatestInfo(canonical_name, latest_info(canonical_name))


def update_all_packages(
    check_outdated: bool = False, 
    list_command_args: list[str] = [], 
    install_command_args: list[str] = [], 
) -> None:
    """Update all installed packages.
    """
    if check_outdated:
        packages = iter_outdated_packages(list_command_args)
    else:
        packages = iter_packages(list_command_args)
    for dist in packages:
        # NOTE: `dist.raw_name` is still available.
        pip_install(*install_command_args, dist.canonical_name, upgrade=True)

