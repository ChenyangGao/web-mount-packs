import errno
from fuse import fuse_exit, log, FUSE # type: ignore

def _wrapper(func, *args, **kwargs):
    'Decorator for the methods that follow'
    func_name = getattr(func, "__name__", "")
    try:
        if func_name == "init":
            # init may not fail, as its return code is just stored as
            # private_data field of struct fuse_context
            return func(*args, **kwargs) or 0
        else:
            try:
                return func(*args, **kwargs) or 0
            except OSError as e:
                if e.errno is None:
                    log.error("Uncaught OSError from FUSE operation %s, "
                                "returning errno.EIO.",
                                func_name, exc_info=True)
                    print(f"{type(e).__qualname__}: {e}")
                    return -errno.EIO
                if e.errno > 0:
                    log.debug(
                        "FUSE operation %s raised a %s, returning errno %s.",
                        func_name, type(e), e.errno, exc_info=True)
                    return -e.errno
                else:
                    log.error(
                        "FUSE operation %s raised an OSError with negative "
                        "errno %s, returning errno.EINVAL.",
                        func_name, e.errno, exc_info=True)
                    return -errno.EINVAL
            except Exception:
                log.error("Uncaught exception from FUSE operation %s, "
                            "returning errno.EINVAL.",
                            func_name, exc_info=True)
                return -errno.EINVAL
    except BaseException as e:
        #self.__critical_exception = e
        log.critical(
            "Uncaught critical exception from FUSE operation %s, aborting.",
            func_name, exc_info=True)
        # the raised exception (even SystemExit) will be caught by FUSE
        # potentially causing SIGSEGV, so tell system to stop/interrupt FUSE
        fuse_exit()
        return -errno.EFAULT

FUSE._wrapper = staticmethod(_wrapper)