#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://github.com/ChenyangGao>"
__all__ = ["ERRNO_TO_MESSAGE", "ERRORTYPE_TO_MESSAGE", "check_response", "DuPanOSError"]

from collections.abc import Awaitable
from errno import EIO
from inspect import isawaitable
from typing import Final


#: 百度网盘 errno 对应的信息
ERRNO_TO_MESSAGE: Final[dict[int, str]] = {
    0: "成功", 
    -1: "由于您分享了违反相关法律法规的文件，分享功能已被禁用，之前分享出去的文件不受影响。", 
    -2: "用户不存在,请刷新页面后重试", 
    -3: "文件不存在,请刷新页面后重试", 
    -4: "登录信息有误，请重新登录试试", 
    -5: "host_key和user_key无效", 
    -6: "请重新登录", 
    -7: "该分享已删除或已取消", 
    -8: "该分享已经过期", 
    -9: "访问密码错误", 
    -10: "分享外链已经达到最大上限100000条，不能再次分享", 
    -11: "验证cookie无效", 
    -12: "参数错误", 
    -14: "对不起，短信分享每天限制20条，你今天已经分享完，请明天再来分享吧！", 
    -15: "对不起，邮件分享每天限制20封，你今天已经分享完，请明天再来分享吧！", 
    -16: "对不起，该文件已经限制分享！", 
    -17: "文件分享超过限制", 
    -21: "预置文件无法进行相关操作", 
    -30: "文件已存在", 
    -31: "文件保存失败", 
    -33: "一次支持操作999个，减点试试吧", 
    -32: "你的空间不足了哟", 
    -62: "需要验证码或者验证码错误", 
    -70: "你分享的文件中包含病毒或疑似病毒，为了你和他人的数据安全，换个文件分享吧", 
    2: "参数错误", 
    3: "未登录或帐号无效", 
    4: "存储好像出问题了，请稍候再试", 
    108: "文件名有敏感词，优化一下吧", 
    110: "分享次数超出限制，可以到“我的分享”中查看已分享的文件链接", 
    114: "当前任务不存在，保存失败", 
    115: "该文件禁止分享", 
    112: '页面已过期，请<a href="javascript:window.location.reload();">刷新</a>后重试', 
    9100: '你的帐号存在违规行为，已被冻结，<a href="/disk/appeal" target="_blank">查看详情</a>', 
    9200: '你的帐号存在违规行为，已被冻结，<a href="/disk/appeal" target="_blank">查看详情</a>', 
    9300: '你的帐号存在违规行为，该功能暂被冻结，<a href="/disk/appeal" target="_blank">查看详情</a>', 
    9400: '你的帐号异常，需验证后才能使用该功能，<a href="/disk/appeal" target="_blank">立即验证</a>', 
    9500: '你的帐号存在安全风险，已进入保护模式，请修改密码后使用，<a href="/disk/appeal" target="_blank">查看详情</a>', 
    90003: "暂无目录管理权限", 
}
#: 百度网盘 errortype 对应的信息
ERRORTYPE_TO_MESSAGE: Final[dict[int, str]] = {
    0: "啊哦，你来晚了，分享的文件已经被删除了，下次要早点哟。", 
    1: "啊哦，你来晚了，分享的文件已经被取消了，下次要早点哟。", 
    2: "此链接分享内容暂时不可访问", 
    3: "此链接分享内容可能因为涉及侵权、色情、反动、低俗等信息，无法访问！", 
    5: "啊哦！链接错误没找到文件，请打开正确的分享链接!", 
    10: "啊哦，来晚了，该分享文件已过期", 
    11: "由于访问次数过多，该分享链接已失效", 
    12: "因该分享含有自动备份目录，暂无法查看", 
    15: "系统升级，链接暂时无法查看，升级完成后恢复正常。", 
    17: "该链接访问范围受限，请使用正常的访问方式", 
    123: "该链接已超过访问人数上限，可联系分享者重新分享", 
    124: "您访问的链接已被冻结，可联系分享者进行激活", 
    -1: "分享的文件不存在。", 
}


class DuPanOSError(OSError):
    ...


def check_response[T: (dict, Awaitable[dict])](resp: T, /) -> T:
    def check(resp: dict, /) -> dict:
        if resp["errno"]:
            resp["errno_reason"] = ERRNO_TO_MESSAGE.get(resp["errno"])
            if "errortype" in ERRORTYPE_TO_MESSAGE:
                resp["errortype_reason"] = ERRORTYPE_TO_MESSAGE.get(resp["errortype"])
            raise DuPanOSError(EIO, resp)
        return resp
    if isawaitable(resp):
        async def call():
            return check(await resp)
        return call()
    return resp

