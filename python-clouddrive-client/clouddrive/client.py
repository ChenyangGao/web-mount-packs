#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["Client", "CLOUDDRIVE_API_MAP"]

from collections.abc import Coroutine
from functools import cached_property
from typing import overload, Any, Iterable, Literal, Never, Sequence
from urllib.parse import urlsplit, urlunsplit

from google.protobuf.empty_pb2 import Empty # type: ignore
from google.protobuf.json_format import ParseDict # type: ignore
from google.protobuf.message import Message # type: ignore
from grpc import insecure_channel, Channel # type: ignore
from grpclib.client import Channel as AsyncChannel # type: ignore
from yarl import URL

import pathlib, sys
PROTO_DIR = str(pathlib.Path(__file__).parent / "proto")
if PROTO_DIR not in sys.path:
    sys.path.append(PROTO_DIR)

import clouddrive.pb2
from .proto import CloudDrive_grpc, CloudDrive_pb2_grpc


CLOUDDRIVE_API_MAP = {
    "GetSystemInfo": {"return": clouddrive.pb2.CloudDriveSystemInfo}, 
    "GetToken": {"argument": dict | clouddrive.pb2.GetTokenRequest, "return": clouddrive.pb2.JWTToken}, 
    "Login": {"argument": dict | clouddrive.pb2.UserLoginRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "Register": {"argument": dict | clouddrive.pb2.UserRegisterRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "SendResetAccountEmail": {"argument": dict | clouddrive.pb2.SendResetAccountEmailRequest}, 
    "ResetAccount": {"argument": dict | clouddrive.pb2.ResetAccountRequest}, 
    "SendConfirmEmail": {}, 
    "ConfirmEmail": {"argument": dict | clouddrive.pb2.ConfirmEmailRequest}, 
    "GetAccountStatus": {"return": clouddrive.pb2.AccountStatusResult}, 
    "GetSubFiles": {"argument": dict | clouddrive.pb2.ListSubFileRequest, "return": Iterable[clouddrive.pb2.SubFilesReply]}, 
    "GetSearchResults": {"argument": dict | clouddrive.pb2.SearchRequest, "return": Iterable[clouddrive.pb2.SubFilesReply]}, 
    "FindFileByPath": {"argument": dict | clouddrive.pb2.FindFileByPathRequest, "return": clouddrive.pb2.CloudDriveFile}, 
    "CreateFolder": {"argument": dict | clouddrive.pb2.CreateFolderRequest, "return": clouddrive.pb2.CreateFolderResult}, 
    "CreateEncryptedFolder": {"argument": dict | clouddrive.pb2.CreateEncryptedFolderRequest, "return": clouddrive.pb2.CreateFolderResult}, 
    "UnlockEncryptedFile": {"argument": dict | clouddrive.pb2.UnlockEncryptedFileRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "LockEncryptedFile": {"argument": dict | clouddrive.pb2.FileRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "RenameFile": {"argument": dict | clouddrive.pb2.RenameFileRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "RenameFiles": {"argument": dict | clouddrive.pb2.RenameFilesRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "MoveFile": {"argument": dict | clouddrive.pb2.MoveFileRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "CopyFile": {"argument": dict | clouddrive.pb2.CopyFileRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "DeleteFile": {"argument": dict | clouddrive.pb2.FileRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "DeleteFilePermanently": {"argument": dict | clouddrive.pb2.FileRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "DeleteFiles": {"argument": dict | clouddrive.pb2.MultiFileRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "DeleteFilesPermanently": {"argument": dict | clouddrive.pb2.MultiFileRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "AddOfflineFiles": {"argument": dict | clouddrive.pb2.AddOfflineFileRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "RemoveOfflineFiles": {"argument": dict | clouddrive.pb2.RemoveOfflineFilesRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "ListOfflineFilesByPath": {"argument": dict | clouddrive.pb2.FileRequest, "return": clouddrive.pb2.OfflineFileListResult}, 
    "ListAllOfflineFiles": {"argument": dict | clouddrive.pb2.OfflineFileListAllRequest, "return": clouddrive.pb2.OfflineFileListAllResult}, 
    "AddSharedLink": {"argument": dict | clouddrive.pb2.AddSharedLinkRequest}, 
    "GetFileDetailProperties": {"argument": dict | clouddrive.pb2.FileRequest, "return": clouddrive.pb2.FileDetailProperties}, 
    "GetSpaceInfo": {"argument": dict | clouddrive.pb2.FileRequest, "return": clouddrive.pb2.SpaceInfo}, 
    "GetCloudMemberships": {"argument": dict | clouddrive.pb2.FileRequest, "return": clouddrive.pb2.CloudMemberships}, 
    "GetRuntimeInfo": {"return": clouddrive.pb2.RuntimeInfo}, 
    "GetRunningInfo": {"return": clouddrive.pb2.RunInfo}, 
    "Logout": {"argument": dict | clouddrive.pb2.UserLogoutRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "CanAddMoreMountPoints": {"return": clouddrive.pb2.FileOperationResult}, 
    "GetMountPoints": {"return": clouddrive.pb2.GetMountPointsResult}, 
    "AddMountPoint": {"argument": dict | clouddrive.pb2.MountOption, "return": clouddrive.pb2.MountPointResult}, 
    "RemoveMountPoint": {"argument": dict | clouddrive.pb2.MountPointRequest, "return": clouddrive.pb2.MountPointResult}, 
    "Mount": {"argument": dict | clouddrive.pb2.MountPointRequest, "return": clouddrive.pb2.MountPointResult}, 
    "Unmount": {"argument": dict | clouddrive.pb2.MountPointRequest, "return": clouddrive.pb2.MountPointResult}, 
    "UpdateMountPoint": {"argument": dict | clouddrive.pb2.UpdateMountPointRequest, "return": clouddrive.pb2.MountPointResult}, 
    "GetAvailableDriveLetters": {"return": clouddrive.pb2.GetAvailableDriveLettersResult}, 
    "HasDriveLetters": {"return": clouddrive.pb2.HasDriveLettersResult}, 
    "LocalGetSubFiles": {"argument": dict | clouddrive.pb2.LocalGetSubFilesRequest, "return": Iterable[clouddrive.pb2.LocalGetSubFilesResult]}, 
    "GetAllTasksCount": {"return": clouddrive.pb2.GetAllTasksCountResult}, 
    "GetDownloadFileCount": {"return": clouddrive.pb2.GetDownloadFileCountResult}, 
    "GetDownloadFileList": {"return": clouddrive.pb2.GetDownloadFileListResult}, 
    "GetUploadFileCount": {"return": clouddrive.pb2.GetUploadFileCountResult}, 
    "GetUploadFileList": {"argument": dict | clouddrive.pb2.GetUploadFileListRequest, "return": clouddrive.pb2.GetUploadFileListResult}, 
    "CancelAllUploadFiles": {}, 
    "CancelUploadFiles": {"argument": dict | clouddrive.pb2.MultpleUploadFileKeyRequest}, 
    "PauseAllUploadFiles": {}, 
    "PauseUploadFiles": {"argument": dict | clouddrive.pb2.MultpleUploadFileKeyRequest}, 
    "ResumeAllUploadFiles": {}, 
    "ResumeUploadFiles": {"argument": dict | clouddrive.pb2.MultpleUploadFileKeyRequest}, 
    "CanAddMoreCloudApis": {"return": clouddrive.pb2.FileOperationResult}, 
    "APILogin115Editthiscookie": {"argument": dict | clouddrive.pb2.Login115EditthiscookieRequest, "return": clouddrive.pb2.APILoginResult}, 
    "APILogin115QRCode": {"argument": dict | clouddrive.pb2.Login115QrCodeRequest, "return": Iterable[clouddrive.pb2.QRCodeScanMessage]}, 
    "APILoginAliyundriveOAuth": {"argument": dict | clouddrive.pb2.LoginAliyundriveOAuthRequest, "return": clouddrive.pb2.APILoginResult}, 
    "APILoginAliyundriveRefreshtoken": {"argument": dict | clouddrive.pb2.LoginAliyundriveRefreshtokenRequest, "return": clouddrive.pb2.APILoginResult}, 
    "APILoginAliyunDriveQRCode": {"argument": dict | clouddrive.pb2.LoginAliyundriveQRCodeRequest, "return": Iterable[clouddrive.pb2.QRCodeScanMessage]}, 
    "APILoginBaiduPanOAuth": {"argument": dict | clouddrive.pb2.LoginBaiduPanOAuthRequest, "return": clouddrive.pb2.APILoginResult}, 
    "APILoginOneDriveOAuth": {"argument": dict | clouddrive.pb2.LoginOneDriveOAuthRequest, "return": clouddrive.pb2.APILoginResult}, 
    "ApiLoginGoogleDriveOAuth": {"argument": dict | clouddrive.pb2.LoginGoogleDriveOAuthRequest, "return": clouddrive.pb2.APILoginResult}, 
    "ApiLoginGoogleDriveRefreshToken": {"argument": dict | clouddrive.pb2.LoginGoogleDriveRefreshTokenRequest, "return": clouddrive.pb2.APILoginResult}, 
    "ApiLoginXunleiOAuth": {"argument": dict | clouddrive.pb2.LoginXunleiOAuthRequest, "return": clouddrive.pb2.APILoginResult}, 
    "ApiLogin123panOAuth": {"argument": dict | clouddrive.pb2.Login123panOAuthRequest, "return": clouddrive.pb2.APILoginResult}, 
    "APILogin189QRCode": {"return": Iterable[clouddrive.pb2.QRCodeScanMessage]}, 
    "APILoginWebDav": {"argument": dict | clouddrive.pb2.LoginWebDavRequest, "return": clouddrive.pb2.APILoginResult}, 
    "APIAddLocalFolder": {"argument": dict | clouddrive.pb2.AddLocalFolderRequest, "return": clouddrive.pb2.APILoginResult}, 
    "RemoveCloudAPI": {"argument": dict | clouddrive.pb2.RemoveCloudAPIRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "GetAllCloudApis": {"return": clouddrive.pb2.CloudAPIList}, 
    "GetCloudAPIConfig": {"argument": dict | clouddrive.pb2.GetCloudAPIConfigRequest, "return": clouddrive.pb2.CloudAPIConfig}, 
    "SetCloudAPIConfig": {"argument": dict | clouddrive.pb2.SetCloudAPIConfigRequest}, 
    "GetSystemSettings": {"return": clouddrive.pb2.SystemSettings}, 
    "SetSystemSettings": {"argument": dict | clouddrive.pb2.SystemSettings}, 
    "SetDirCacheTimeSecs": {"argument": dict | clouddrive.pb2.SetDirCacheTimeRequest}, 
    "GetEffectiveDirCacheTimeSecs": {"argument": dict | clouddrive.pb2.GetEffectiveDirCacheTimeRequest, "return": clouddrive.pb2.GetEffectiveDirCacheTimeResult}, 
    "ForceExpireDirCache": {"argument": dict | clouddrive.pb2.FileRequest}, 
    "GetOpenFileTable": {"argument": dict | clouddrive.pb2.GetOpenFileTableRequest, "return": clouddrive.pb2.OpenFileTable}, 
    "GetDirCacheTable": {"return": clouddrive.pb2.DirCacheTable}, 
    "GetReferencedEntryPaths": {"argument": dict | clouddrive.pb2.FileRequest, "return": clouddrive.pb2.StringList}, 
    "GetTempFileTable": {"return": clouddrive.pb2.TempFileTable}, 
    "PushTaskChange": {"return": Iterable[clouddrive.pb2.GetAllTasksCountResult]}, 
    "PushMessage": {"return": Iterable[clouddrive.pb2.CloudDrivePushMessage]}, 
    "GetCloudDrive1UserData": {"return": clouddrive.pb2.StringResult}, 
    "RestartService": {}, 
    "ShutdownService": {}, 
    "HasUpdate": {"return": clouddrive.pb2.UpdateResult}, 
    "CheckUpdate": {"return": clouddrive.pb2.UpdateResult}, 
    "DownloadUpdate": {}, 
    "UpdateSystem": {}, 
    "TestUpdate": {"argument": dict | clouddrive.pb2.FileRequest}, 
    "GetMetaData": {"argument": dict | clouddrive.pb2.FileRequest, "return": clouddrive.pb2.FileMetaData}, 
    "GetOriginalPath": {"argument": dict | clouddrive.pb2.FileRequest, "return": clouddrive.pb2.StringResult}, 
    "ChangePassword": {"argument": dict | clouddrive.pb2.ChangePasswordRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "CreateFile": {"argument": dict | clouddrive.pb2.CreateFileRequest, "return": clouddrive.pb2.CreateFileResult}, 
    "CloseFile": {"argument": dict | clouddrive.pb2.CloseFileRequest, "return": clouddrive.pb2.FileOperationResult}, 
    "WriteToFileStream": {"argument": Sequence[dict | clouddrive.pb2.WriteFileRequest], "return": clouddrive.pb2.WriteFileResult}, 
    "WriteToFile": {"argument": dict | clouddrive.pb2.WriteFileRequest, "return": clouddrive.pb2.WriteFileResult}, 
    "GetPromotions": {"return": clouddrive.pb2.GetPromotionsResult}, 
    "UpdatePromotionResult": {}, 
    "GetCloudDrivePlans": {"return": clouddrive.pb2.GetCloudDrivePlansResult}, 
    "JoinPlan": {"argument": dict | clouddrive.pb2.JoinPlanRequest, "return": clouddrive.pb2.JoinPlanResult}, 
    "BindCloudAccount": {"argument": dict | clouddrive.pb2.BindCloudAccountRequest}, 
    "TransferBalance": {"argument": dict | clouddrive.pb2.TransferBalanceRequest}, 
    "ChangeEmail": {"argument": dict | clouddrive.pb2.ChangeUserNameEmailRequest}, 
    "GetBalanceLog": {"return": clouddrive.pb2.BalanceLogResult}, 
    "CheckActivationCode": {"argument": dict | clouddrive.pb2.StringValue, "return": clouddrive.pb2.CheckActivationCodeResult}, 
    "ActivatePlan": {"argument": dict | clouddrive.pb2.StringValue, "return": clouddrive.pb2.JoinPlanResult}, 
    "CheckCouponCode": {"argument": dict | clouddrive.pb2.CheckCouponCodeRequest, "return": clouddrive.pb2.CouponCodeResult}, 
    "GetReferralCode": {"return": clouddrive.pb2.StringValue}, 
    "BackupGetAll": {"return": clouddrive.pb2.BackupList}, 
    "BackupAdd": {"argument": dict | clouddrive.pb2.Backup}, 
    "BackupRemove": {"argument": dict | clouddrive.pb2.StringValue}, 
    "BackupUpdate": {"argument": dict | clouddrive.pb2.Backup}, 
    "BackupAddDestination": {"argument": dict | clouddrive.pb2.BackupModifyRequest}, 
    "BackupRemoveDestination": {"argument": dict | clouddrive.pb2.BackupModifyRequest}, 
    "BackupSetEnabled": {"argument": dict | clouddrive.pb2.BackupSetEnabledRequest}, 
    "BackupSetFileSystemWatchEnabled": {"argument": dict | clouddrive.pb2.BackupModifyRequest}, 
    "BackupUpdateStrategies": {"argument": dict | clouddrive.pb2.BackupModifyRequest}, 
    "BackupRestartWalkingThrough": {"argument": dict | clouddrive.pb2.StringValue}, 
    "CanAddMoreBackups": {"return": clouddrive.pb2.FileOperationResult}, 
    "GetMachineId": {"return": clouddrive.pb2.StringResult}, 
    "GetOnlineDevices": {"return": clouddrive.pb2.OnlineDevices}, 
    "KickoutDevice": {"argument": dict | clouddrive.pb2.DeviceRequest}, 
    "ListLogFiles": {"return": clouddrive.pb2.ListLogFileResult}, 
    "SyncFileChangesFromCloud": {"argument": dict | clouddrive.pb2.FileRequest, "return": clouddrive.pb2.FileSystemChangeStatistics}, 
}


def to_message(cls, o, /) -> Message:
    if isinstance(o, Message):
        return o
    elif type(o) is dict:
        return ParseDict(o, cls())
    elif type(o) is tuple:
        return cls(**{f.name: a for f, a in zip(cls.DESCRIPTOR.fields, o)})
    else:
        return cls(**{cls.DESCRIPTOR.fields[0].name: o})


class Client:
    "clouddrive client that encapsulates grpc APIs"
    origin: URL
    username: str
    password: str
    download_baseurl: str
    metadata: list[tuple[str, str]]

    def __init__(
        self, 
        /, 
        origin: str = "http://localhost:19798", 
        username: str = "", 
        password: str = "", 
    ):
        origin = origin.rstrip("/")
        urlp = urlsplit(origin)
        scheme = urlp.scheme or "http"
        netloc = urlp.netloc or "localhost:19798"
        self.__dict__.update(
            origin = URL(urlunsplit(urlp._replace(scheme=scheme, netloc=netloc))), 
            download_baseurl = f"{scheme}://{netloc}/static/{scheme}/{netloc}/False/", 
            username = username, 
            password = password, 
            metadata = [], 
        )
        if username:
            self.login()

    def __del__(self, /):
        self.close()

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.origin == other.origin and self.username == other.username

    def __hash__(self, /) -> int:
        return hash((self.origin, self.username))

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(origin={self.origin!r}, username={self.username!r}, password='******')"

    def __setattr__(self, attr, val, /) -> Never:
        raise TypeError("can't set attribute")

    @cached_property
    def channel(self, /) -> Channel:
        return insecure_channel(self.origin.authority)

    @cached_property
    def stub(self, /) -> clouddrive.proto.CloudDrive_pb2_grpc.CloudDriveFileSrvStub:
        return CloudDrive_pb2_grpc.CloudDriveFileSrvStub(self.channel)

    @cached_property
    def async_channel(self, /) -> AsyncChannel:
        origin = self.origin
        return AsyncChannel(origin.host, origin.port)

    @cached_property
    def async_stub(self, /) -> clouddrive.proto.CloudDrive_grpc.CloudDriveFileSrvStub:
        return CloudDrive_grpc.CloudDriveFileSrvStub(self.async_channel)

    def close(self, /):
        ns = self.__dict__
        if "channel" in ns:
            ns["channel"].close()
        if "async_channel" in ns:
            ns["async_channel"].close()

    def set_password(self, value: str, /):
        self.__dict__["password"] = value
        self.login()

    def login(
        self, 
        /, 
        username: str = "", 
        password: str = "", 
    ):
        if not username:
            username = self.username
        if not password:
            password = self.password
        response = self.stub.GetToken(clouddrive.pb2.GetTokenRequest(userName=username, password=password))
        self.metadata[:] = [("authorization", "Bearer " + response.token),]

    @overload
    def GetSystemInfo(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.CloudDriveSystemInfo:
        ...
    @overload
    def GetSystemInfo(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.CloudDriveSystemInfo]:
        ...
    def GetSystemInfo(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.CloudDriveSystemInfo | Coroutine[Any, Any, clouddrive.pb2.CloudDriveSystemInfo]:
        """
        public methods, no authorization is required
        returns if clouddrive has logged in to cloudfs server and the user name

        ------------------- protobuf rpc definition --------------------

        // public methods, no authorization is required
        // returns if clouddrive has logged in to cloudfs server and the user name
        rpc GetSystemInfo(google.protobuf.Empty) returns (CloudDriveSystemInfo) {}

        ------------------- protobuf type definition -------------------

        message CloudDriveSystemInfo {
          bool IsLogin = 1;
          string UserName = 2;
        }
        """
        if async_:
            return self.async_stub.GetSystemInfo(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetSystemInfo(Empty(), metadata=self.metadata)

    @overload
    def GetToken(
        self, 
        arg: dict | clouddrive.pb2.GetTokenRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.JWTToken:
        ...
    @overload
    def GetToken(
        self, 
        arg: dict | clouddrive.pb2.GetTokenRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.JWTToken]:
        ...
    def GetToken(
        self, 
        arg: dict | clouddrive.pb2.GetTokenRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.JWTToken | Coroutine[Any, Any, clouddrive.pb2.JWTToken]:
        """
        get bearer token by username and password

        ------------------- protobuf rpc definition --------------------

        // get bearer token by username and password
        rpc GetToken(GetTokenRequest) returns (JWTToken) {}

        ------------------- protobuf type definition -------------------

        message GetTokenRequest {
          string userName = 1;
          string password = 2;
        }
        message JWTToken {
          bool success = 1;
          string errorMessage = 2;
          string token = 3;
          google.protobuf.Timestamp expiration = 4;
        }
        """
        arg = to_message(clouddrive.pb2.GetTokenRequest, arg)
        if async_:
            return self.async_stub.GetToken(arg, metadata=self.metadata)
        else:
            return self.stub.GetToken(arg, metadata=self.metadata)

    @overload
    def Login(
        self, 
        arg: dict | clouddrive.pb2.UserLoginRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def Login(
        self, 
        arg: dict | clouddrive.pb2.UserLoginRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def Login(
        self, 
        arg: dict | clouddrive.pb2.UserLoginRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        login to cloudfs server

        ------------------- protobuf rpc definition --------------------

        // login to cloudfs server
        rpc Login(UserLoginRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message UserLoginRequest {
          string userName = 1;
          string password = 2;
          bool synDataToCloud = 3;
        }
        """
        arg = to_message(clouddrive.pb2.UserLoginRequest, arg)
        if async_:
            return self.async_stub.Login(arg, metadata=self.metadata)
        else:
            return self.stub.Login(arg, metadata=self.metadata)

    @overload
    def Register(
        self, 
        arg: dict | clouddrive.pb2.UserRegisterRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def Register(
        self, 
        arg: dict | clouddrive.pb2.UserRegisterRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def Register(
        self, 
        arg: dict | clouddrive.pb2.UserRegisterRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        register a new count

        ------------------- protobuf rpc definition --------------------

        // register a new count
        rpc Register(UserRegisterRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message UserRegisterRequest {
          string userName = 1;
          string password = 2;
        }
        """
        arg = to_message(clouddrive.pb2.UserRegisterRequest, arg)
        if async_:
            return self.async_stub.Register(arg, metadata=self.metadata)
        else:
            return self.stub.Register(arg, metadata=self.metadata)

    @overload
    def SendResetAccountEmail(
        self, 
        arg: dict | clouddrive.pb2.SendResetAccountEmailRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def SendResetAccountEmail(
        self, 
        arg: dict | clouddrive.pb2.SendResetAccountEmailRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def SendResetAccountEmail(
        self, 
        arg: dict | clouddrive.pb2.SendResetAccountEmailRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        asks cloudfs server to send reset account email with reset link

        ------------------- protobuf rpc definition --------------------

        // asks cloudfs server to send reset account email with reset link
        rpc SendResetAccountEmail(SendResetAccountEmailRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message SendResetAccountEmailRequest { string email = 1; }
        """
        if async_:
            async def request():
                await self.async_stub.SendResetAccountEmail(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.SendResetAccountEmail(arg, metadata=self.metadata)
            return None

    @overload
    def ResetAccount(
        self, 
        arg: dict | clouddrive.pb2.ResetAccountRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def ResetAccount(
        self, 
        arg: dict | clouddrive.pb2.ResetAccountRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def ResetAccount(
        self, 
        arg: dict | clouddrive.pb2.ResetAccountRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        reset account's data, set new password, with received reset code from email

        ------------------- protobuf rpc definition --------------------

        // reset account's data, set new password, with received reset code from email
        rpc ResetAccount(ResetAccountRequest) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message ResetAccountRequest {
          string resetCode = 1;
          string newPassword = 2;
        }
        """
        if async_:
            async def request():
                await self.async_stub.ResetAccount(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.ResetAccount(arg, metadata=self.metadata)
            return None

    @overload
    def SendConfirmEmail(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def SendConfirmEmail(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def SendConfirmEmail(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        authorized methods, Authorization header with Bearer {token} is requirerd
        asks cloudfs server to send confirm email with confirm link

        ------------------- protobuf rpc definition --------------------

        // authorized methods, Authorization header with Bearer {token} is requirerd
        // asks cloudfs server to send confirm email with confirm link
        rpc SendConfirmEmail(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        if async_:
            async def request():
                await self.async_stub.SendConfirmEmail(Empty(), metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.SendConfirmEmail(Empty(), metadata=self.metadata)
            return None

    @overload
    def ConfirmEmail(
        self, 
        arg: dict | clouddrive.pb2.ConfirmEmailRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def ConfirmEmail(
        self, 
        arg: dict | clouddrive.pb2.ConfirmEmailRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def ConfirmEmail(
        self, 
        arg: dict | clouddrive.pb2.ConfirmEmailRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        confirm email by confirm code

        ------------------- protobuf rpc definition --------------------

        // confirm email by confirm code
        rpc ConfirmEmail(ConfirmEmailRequest) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message ConfirmEmailRequest { string confirmCode = 1; }
        """
        if async_:
            async def request():
                await self.async_stub.ConfirmEmail(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.ConfirmEmail(arg, metadata=self.metadata)
            return None

    @overload
    def GetAccountStatus(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.AccountStatusResult:
        ...
    @overload
    def GetAccountStatus(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.AccountStatusResult]:
        ...
    def GetAccountStatus(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.AccountStatusResult | Coroutine[Any, Any, clouddrive.pb2.AccountStatusResult]:
        """
        get account status

        ------------------- protobuf rpc definition --------------------

        // get account status
        rpc GetAccountStatus(google.protobuf.Empty) returns (AccountStatusResult) {}

        ------------------- protobuf type definition -------------------

        message AccountPlan {
          string planName = 1;
          string description = 2;
          string fontAwesomeIcon = 3;
          string durationDescription = 4;
          google.protobuf.Timestamp endTime = 5;
        }
        message AccountRole {
          string roleName = 1;
          string description = 2;
          optional int32 value = 3;
        }
        message AccountStatusResult {
          string userName = 1;
          string emailConfirmed = 2;
          double accountBalance = 3;
          AccountPlan accountPlan = 4;
          repeated AccountRole accountRoles = 5;
          optional AccountPlan secondPlan = 6;
          optional string partnerReferralCode = 7;
        }
        """
        if async_:
            return self.async_stub.GetAccountStatus(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetAccountStatus(Empty(), metadata=self.metadata)

    @overload
    def GetSubFiles(
        self, 
        arg: dict | clouddrive.pb2.ListSubFileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> Iterable[clouddrive.pb2.SubFilesReply]:
        ...
    @overload
    def GetSubFiles(
        self, 
        arg: dict | clouddrive.pb2.ListSubFileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Iterable[clouddrive.pb2.SubFilesReply]]:
        ...
    def GetSubFiles(
        self, 
        arg: dict | clouddrive.pb2.ListSubFileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Iterable[clouddrive.pb2.SubFilesReply] | Coroutine[Any, Any, Iterable[clouddrive.pb2.SubFilesReply]]:
        """
        get all subfiles by path

        ------------------- protobuf rpc definition --------------------

        // get all subfiles by path
        rpc GetSubFiles(ListSubFileRequest) returns (stream SubFilesReply) {}

        ------------------- protobuf type definition -------------------

        message CloudDriveFile {
          string id = 1;
          string name = 2;
          string fullPathName = 3;
          int64 size = 4;
          enum FileType {
            Directory = 0;
            File = 1;
            Other = 2;
          }
          FileType fileType = 5;
          google.protobuf.Timestamp createTime = 6;
          google.protobuf.Timestamp writeTime = 7;
          google.protobuf.Timestamp accessTime = 8;
          CloudAPI CloudAPI = 9;
          string thumbnailUrl = 10;
          string previewUrl = 11;
          string originalPath = 14;

          bool isDirectory = 30;
          bool isRoot = 31;
          bool isCloudRoot = 32;
          bool isCloudDirectory = 33;
          bool isCloudFile = 34;
          bool isSearchResult = 35;
          bool isForbidden = 36;
          bool isLocal = 37;

          bool canMount = 60;
          bool canUnmount = 61;
          bool canDirectAccessThumbnailURL = 62;
          bool canSearch = 63;
          bool hasDetailProperties = 64;
          FileDetailProperties detailProperties = 65;
          bool canOfflineDownload = 66;
          bool canAddShareLink = 67;
          optional uint64 dirCacheTimeToLiveSecs = 68;
          bool canDeletePermanently = 69;
          enum HashType {
            Unknown = 0;
            Md5 = 1;
            Sha1 = 2;
            PikPakSha1 = 3;
          }
          map<uint32, string> fileHashes = 70;
          enum FileEncryptionType {
            None = 0; // not encrypted
            Encrypted = 1; // encrypted, password not provided, a password is required to unlock the file 
            Unlocked = 2; // encrypted but but password is provided, can access the file
          }
          FileEncryptionType fileEncryptionType = 71;
          bool CanCreateEncryptedFolder = 72;
          bool CanLock = 73; // An unlocked encrypted file/folder can be locked
          bool CanSyncFileChangesFromCloud = 74; // File change can be synced from cloud
        }
        message ListSubFileRequest {
          string path = 1;
          bool forceRefresh = 2;
          optional bool checkExpires = 3;
        }
        message SubFilesReply { repeated CloudDriveFile subFiles = 1; }
        """
        arg = to_message(clouddrive.pb2.ListSubFileRequest, arg)
        if async_:
            return self.async_stub.GetSubFiles(arg, metadata=self.metadata)
        else:
            return self.stub.GetSubFiles(arg, metadata=self.metadata)

    @overload
    def GetSearchResults(
        self, 
        arg: dict | clouddrive.pb2.SearchRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> Iterable[clouddrive.pb2.SubFilesReply]:
        ...
    @overload
    def GetSearchResults(
        self, 
        arg: dict | clouddrive.pb2.SearchRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Iterable[clouddrive.pb2.SubFilesReply]]:
        ...
    def GetSearchResults(
        self, 
        arg: dict | clouddrive.pb2.SearchRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Iterable[clouddrive.pb2.SubFilesReply] | Coroutine[Any, Any, Iterable[clouddrive.pb2.SubFilesReply]]:
        """
        search under path

        ------------------- protobuf rpc definition --------------------

        // search under path
        rpc GetSearchResults(SearchRequest) returns (stream SubFilesReply) {}

        ------------------- protobuf type definition -------------------

        message CloudDriveFile {
          string id = 1;
          string name = 2;
          string fullPathName = 3;
          int64 size = 4;
          enum FileType {
            Directory = 0;
            File = 1;
            Other = 2;
          }
          FileType fileType = 5;
          google.protobuf.Timestamp createTime = 6;
          google.protobuf.Timestamp writeTime = 7;
          google.protobuf.Timestamp accessTime = 8;
          CloudAPI CloudAPI = 9;
          string thumbnailUrl = 10;
          string previewUrl = 11;
          string originalPath = 14;

          bool isDirectory = 30;
          bool isRoot = 31;
          bool isCloudRoot = 32;
          bool isCloudDirectory = 33;
          bool isCloudFile = 34;
          bool isSearchResult = 35;
          bool isForbidden = 36;
          bool isLocal = 37;

          bool canMount = 60;
          bool canUnmount = 61;
          bool canDirectAccessThumbnailURL = 62;
          bool canSearch = 63;
          bool hasDetailProperties = 64;
          FileDetailProperties detailProperties = 65;
          bool canOfflineDownload = 66;
          bool canAddShareLink = 67;
          optional uint64 dirCacheTimeToLiveSecs = 68;
          bool canDeletePermanently = 69;
          enum HashType {
            Unknown = 0;
            Md5 = 1;
            Sha1 = 2;
            PikPakSha1 = 3;
          }
          map<uint32, string> fileHashes = 70;
          enum FileEncryptionType {
            None = 0; // not encrypted
            Encrypted = 1; // encrypted, password not provided, a password is required to unlock the file 
            Unlocked = 2; // encrypted but but password is provided, can access the file
          }
          FileEncryptionType fileEncryptionType = 71;
          bool CanCreateEncryptedFolder = 72;
          bool CanLock = 73; // An unlocked encrypted file/folder can be locked
          bool CanSyncFileChangesFromCloud = 74; // File change can be synced from cloud
        }
        message SearchRequest {
          string path = 1;
          string searchFor = 2;
          bool forceRefresh = 3;
          bool fuzzyMatch = 4;
        }
        message SubFilesReply { repeated CloudDriveFile subFiles = 1; }
        """
        arg = to_message(clouddrive.pb2.SearchRequest, arg)
        if async_:
            return self.async_stub.GetSearchResults(arg, metadata=self.metadata)
        else:
            return self.stub.GetSearchResults(arg, metadata=self.metadata)

    @overload
    def FindFileByPath(
        self, 
        arg: dict | clouddrive.pb2.FindFileByPathRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.CloudDriveFile:
        ...
    @overload
    def FindFileByPath(
        self, 
        arg: dict | clouddrive.pb2.FindFileByPathRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.CloudDriveFile]:
        ...
    def FindFileByPath(
        self, 
        arg: dict | clouddrive.pb2.FindFileByPathRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.CloudDriveFile | Coroutine[Any, Any, clouddrive.pb2.CloudDriveFile]:
        """
        find file info by full path

        ------------------- protobuf rpc definition --------------------

        // find file info by full path
        rpc FindFileByPath(FindFileByPathRequest) returns (CloudDriveFile) {}

        ------------------- protobuf type definition -------------------

        message CloudAPI {
          string name = 1;
          string userName = 2;
          string nickName = 3;
          bool isLocked = 4; // isLocked means the cloudAPI is set to can't open files,
                             // due to user's membership issue
          bool supportMultiThreadUploading = 5;
          bool supportQpsLimit = 6;
          bool isCloudEventListenerRunning = 7;
        }
        message CloudDriveFile {
          string id = 1;
          string name = 2;
          string fullPathName = 3;
          int64 size = 4;
          enum FileType {
            Directory = 0;
            File = 1;
            Other = 2;
          }
          FileType fileType = 5;
          google.protobuf.Timestamp createTime = 6;
          google.protobuf.Timestamp writeTime = 7;
          google.protobuf.Timestamp accessTime = 8;
          CloudAPI CloudAPI = 9;
          string thumbnailUrl = 10;
          string previewUrl = 11;
          string originalPath = 14;

          bool isDirectory = 30;
          bool isRoot = 31;
          bool isCloudRoot = 32;
          bool isCloudDirectory = 33;
          bool isCloudFile = 34;
          bool isSearchResult = 35;
          bool isForbidden = 36;
          bool isLocal = 37;

          bool canMount = 60;
          bool canUnmount = 61;
          bool canDirectAccessThumbnailURL = 62;
          bool canSearch = 63;
          bool hasDetailProperties = 64;
          FileDetailProperties detailProperties = 65;
          bool canOfflineDownload = 66;
          bool canAddShareLink = 67;
          optional uint64 dirCacheTimeToLiveSecs = 68;
          bool canDeletePermanently = 69;
          enum HashType {
            Unknown = 0;
            Md5 = 1;
            Sha1 = 2;
            PikPakSha1 = 3;
          }
          map<uint32, string> fileHashes = 70;
          enum FileEncryptionType {
            None = 0; // not encrypted
            Encrypted = 1; // encrypted, password not provided, a password is required to unlock the file 
            Unlocked = 2; // encrypted but but password is provided, can access the file
          }
          FileEncryptionType fileEncryptionType = 71;
          bool CanCreateEncryptedFolder = 72;
          bool CanLock = 73; // An unlocked encrypted file/folder can be locked
          bool CanSyncFileChangesFromCloud = 74; // File change can be synced from cloud
        }
        message FileDetailProperties {
          int64 totalFileCount = 1;
          int64 totalFolderCount = 2;
          int64 totalSize = 3;
          bool isFaved = 4;
          bool isShared = 5;
          string originalPath = 6;
        }
        message FindFileByPathRequest {
          string parentPath = 1;
          string path = 2;
        }
        """
        arg = to_message(clouddrive.pb2.FindFileByPathRequest, arg)
        if async_:
            return self.async_stub.FindFileByPath(arg, metadata=self.metadata)
        else:
            return self.stub.FindFileByPath(arg, metadata=self.metadata)

    @overload
    def CreateFolder(
        self, 
        arg: dict | clouddrive.pb2.CreateFolderRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.CreateFolderResult:
        ...
    @overload
    def CreateFolder(
        self, 
        arg: dict | clouddrive.pb2.CreateFolderRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.CreateFolderResult]:
        ...
    def CreateFolder(
        self, 
        arg: dict | clouddrive.pb2.CreateFolderRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.CreateFolderResult | Coroutine[Any, Any, clouddrive.pb2.CreateFolderResult]:
        """
        create a folder under path

        ------------------- protobuf rpc definition --------------------

        // create a folder under path
        rpc CreateFolder(CreateFolderRequest) returns (CreateFolderResult) {}

        ------------------- protobuf type definition -------------------

        message CloudDriveFile {
          string id = 1;
          string name = 2;
          string fullPathName = 3;
          int64 size = 4;
          enum FileType {
            Directory = 0;
            File = 1;
            Other = 2;
          }
          FileType fileType = 5;
          google.protobuf.Timestamp createTime = 6;
          google.protobuf.Timestamp writeTime = 7;
          google.protobuf.Timestamp accessTime = 8;
          CloudAPI CloudAPI = 9;
          string thumbnailUrl = 10;
          string previewUrl = 11;
          string originalPath = 14;

          bool isDirectory = 30;
          bool isRoot = 31;
          bool isCloudRoot = 32;
          bool isCloudDirectory = 33;
          bool isCloudFile = 34;
          bool isSearchResult = 35;
          bool isForbidden = 36;
          bool isLocal = 37;

          bool canMount = 60;
          bool canUnmount = 61;
          bool canDirectAccessThumbnailURL = 62;
          bool canSearch = 63;
          bool hasDetailProperties = 64;
          FileDetailProperties detailProperties = 65;
          bool canOfflineDownload = 66;
          bool canAddShareLink = 67;
          optional uint64 dirCacheTimeToLiveSecs = 68;
          bool canDeletePermanently = 69;
          enum HashType {
            Unknown = 0;
            Md5 = 1;
            Sha1 = 2;
            PikPakSha1 = 3;
          }
          map<uint32, string> fileHashes = 70;
          enum FileEncryptionType {
            None = 0; // not encrypted
            Encrypted = 1; // encrypted, password not provided, a password is required to unlock the file 
            Unlocked = 2; // encrypted but but password is provided, can access the file
          }
          FileEncryptionType fileEncryptionType = 71;
          bool CanCreateEncryptedFolder = 72;
          bool CanLock = 73; // An unlocked encrypted file/folder can be locked
          bool CanSyncFileChangesFromCloud = 74; // File change can be synced from cloud
        }
        message CreateFolderRequest {
          string parentPath = 1;
          string folderName = 2;
        }
        message CreateFolderResult {
          CloudDriveFile folderCreated = 1;
          FileOperationResult result = 2;
        }
        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        """
        arg = to_message(clouddrive.pb2.CreateFolderRequest, arg)
        if async_:
            return self.async_stub.CreateFolder(arg, metadata=self.metadata)
        else:
            return self.stub.CreateFolder(arg, metadata=self.metadata)

    @overload
    def CreateEncryptedFolder(
        self, 
        arg: dict | clouddrive.pb2.CreateEncryptedFolderRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.CreateFolderResult:
        ...
    @overload
    def CreateEncryptedFolder(
        self, 
        arg: dict | clouddrive.pb2.CreateEncryptedFolderRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.CreateFolderResult]:
        ...
    def CreateEncryptedFolder(
        self, 
        arg: dict | clouddrive.pb2.CreateEncryptedFolderRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.CreateFolderResult | Coroutine[Any, Any, clouddrive.pb2.CreateFolderResult]:
        """
        create an encrypted folder under path

        ------------------- protobuf rpc definition --------------------

        // create an encrypted folder under path
        rpc CreateEncryptedFolder(CreateEncryptedFolderRequest) returns (CreateFolderResult) {}

        ------------------- protobuf type definition -------------------

        message CloudDriveFile {
          string id = 1;
          string name = 2;
          string fullPathName = 3;
          int64 size = 4;
          enum FileType {
            Directory = 0;
            File = 1;
            Other = 2;
          }
          FileType fileType = 5;
          google.protobuf.Timestamp createTime = 6;
          google.protobuf.Timestamp writeTime = 7;
          google.protobuf.Timestamp accessTime = 8;
          CloudAPI CloudAPI = 9;
          string thumbnailUrl = 10;
          string previewUrl = 11;
          string originalPath = 14;

          bool isDirectory = 30;
          bool isRoot = 31;
          bool isCloudRoot = 32;
          bool isCloudDirectory = 33;
          bool isCloudFile = 34;
          bool isSearchResult = 35;
          bool isForbidden = 36;
          bool isLocal = 37;

          bool canMount = 60;
          bool canUnmount = 61;
          bool canDirectAccessThumbnailURL = 62;
          bool canSearch = 63;
          bool hasDetailProperties = 64;
          FileDetailProperties detailProperties = 65;
          bool canOfflineDownload = 66;
          bool canAddShareLink = 67;
          optional uint64 dirCacheTimeToLiveSecs = 68;
          bool canDeletePermanently = 69;
          enum HashType {
            Unknown = 0;
            Md5 = 1;
            Sha1 = 2;
            PikPakSha1 = 3;
          }
          map<uint32, string> fileHashes = 70;
          enum FileEncryptionType {
            None = 0; // not encrypted
            Encrypted = 1; // encrypted, password not provided, a password is required to unlock the file 
            Unlocked = 2; // encrypted but but password is provided, can access the file
          }
          FileEncryptionType fileEncryptionType = 71;
          bool CanCreateEncryptedFolder = 72;
          bool CanLock = 73; // An unlocked encrypted file/folder can be locked
          bool CanSyncFileChangesFromCloud = 74; // File change can be synced from cloud
        }
        message CreateEncryptedFolderRequest {
          string parentPath = 1;
          string folderName = 2;
          string password = 3;
          bool savePassword = 4; //if true, password will be saved to db, else unlock is required after restart
        }
        message CreateFolderResult {
          CloudDriveFile folderCreated = 1;
          FileOperationResult result = 2;
        }
        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        """
        arg = to_message(clouddrive.pb2.CreateEncryptedFolderRequest, arg)
        if async_:
            return self.async_stub.CreateEncryptedFolder(arg, metadata=self.metadata)
        else:
            return self.stub.CreateEncryptedFolder(arg, metadata=self.metadata)

    @overload
    def UnlockEncryptedFile(
        self, 
        arg: dict | clouddrive.pb2.UnlockEncryptedFileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def UnlockEncryptedFile(
        self, 
        arg: dict | clouddrive.pb2.UnlockEncryptedFileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def UnlockEncryptedFile(
        self, 
        arg: dict | clouddrive.pb2.UnlockEncryptedFileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        unlock an encrypted folder/file by setting password

        ------------------- protobuf rpc definition --------------------

        // unlock an encrypted folder/file by setting password
        rpc UnlockEncryptedFile(UnlockEncryptedFileRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message UnlockEncryptedFileRequest {
          string path = 1;
          string password = 2;
          bool permanentUnlock = 3; //if true, password will be saved to db, else unlock is required after restart
        }
        """
        arg = to_message(clouddrive.pb2.UnlockEncryptedFileRequest, arg)
        if async_:
            return self.async_stub.UnlockEncryptedFile(arg, metadata=self.metadata)
        else:
            return self.stub.UnlockEncryptedFile(arg, metadata=self.metadata)

    @overload
    def LockEncryptedFile(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def LockEncryptedFile(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def LockEncryptedFile(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        lock an encrypted folder/file by clearing password

        ------------------- protobuf rpc definition --------------------

        // lock an encrypted folder/file by clearing password
        rpc LockEncryptedFile(FileRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message FileRequest { string path = 1; }
        """
        arg = to_message(clouddrive.pb2.FileRequest, arg)
        if async_:
            return self.async_stub.LockEncryptedFile(arg, metadata=self.metadata)
        else:
            return self.stub.LockEncryptedFile(arg, metadata=self.metadata)

    @overload
    def RenameFile(
        self, 
        arg: dict | clouddrive.pb2.RenameFileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def RenameFile(
        self, 
        arg: dict | clouddrive.pb2.RenameFileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def RenameFile(
        self, 
        arg: dict | clouddrive.pb2.RenameFileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        rename a single file

        ------------------- protobuf rpc definition --------------------

        // rename a single file
        rpc RenameFile(RenameFileRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message RenameFileRequest {
          string theFilePath = 1;
          string newName = 2;
        }
        """
        arg = to_message(clouddrive.pb2.RenameFileRequest, arg)
        if async_:
            return self.async_stub.RenameFile(arg, metadata=self.metadata)
        else:
            return self.stub.RenameFile(arg, metadata=self.metadata)

    @overload
    def RenameFiles(
        self, 
        arg: dict | clouddrive.pb2.RenameFilesRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def RenameFiles(
        self, 
        arg: dict | clouddrive.pb2.RenameFilesRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def RenameFiles(
        self, 
        arg: dict | clouddrive.pb2.RenameFilesRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        batch rename files

        ------------------- protobuf rpc definition --------------------

        // batch rename files
        rpc RenameFiles(RenameFilesRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message RenameFileRequest {
          string theFilePath = 1;
          string newName = 2;
        }
        message RenameFilesRequest { repeated RenameFileRequest renameFiles = 1; }
        """
        arg = to_message(clouddrive.pb2.RenameFilesRequest, arg)
        if async_:
            return self.async_stub.RenameFiles(arg, metadata=self.metadata)
        else:
            return self.stub.RenameFiles(arg, metadata=self.metadata)

    @overload
    def MoveFile(
        self, 
        arg: dict | clouddrive.pb2.MoveFileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def MoveFile(
        self, 
        arg: dict | clouddrive.pb2.MoveFileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def MoveFile(
        self, 
        arg: dict | clouddrive.pb2.MoveFileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        move files to a dest folder

        ------------------- protobuf rpc definition --------------------

        // move files to a dest folder
        rpc MoveFile(MoveFileRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message MoveFileRequest {
          enum ConflictPolicy {
            Overwrite = 0;
            Rename = 1;
            Skip = 2;
          }
          repeated string theFilePaths = 1;
          string destPath = 2;
          optional ConflictPolicy conflictPolicy = 3;
        }
        """
        arg = to_message(clouddrive.pb2.MoveFileRequest, arg)
        if async_:
            return self.async_stub.MoveFile(arg, metadata=self.metadata)
        else:
            return self.stub.MoveFile(arg, metadata=self.metadata)

    @overload
    def CopyFile(
        self, 
        arg: dict | clouddrive.pb2.CopyFileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def CopyFile(
        self, 
        arg: dict | clouddrive.pb2.CopyFileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def CopyFile(
        self, 
        arg: dict | clouddrive.pb2.CopyFileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        copy files to a dest folder

        ------------------- protobuf rpc definition --------------------

        // copy files to a dest folder
        rpc CopyFile(CopyFileRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message CopyFileRequest {
          repeated string theFilePaths = 1;
          string destPath = 2;
        }
        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        """
        arg = to_message(clouddrive.pb2.CopyFileRequest, arg)
        if async_:
            return self.async_stub.CopyFile(arg, metadata=self.metadata)
        else:
            return self.stub.CopyFile(arg, metadata=self.metadata)

    @overload
    def DeleteFile(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def DeleteFile(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def DeleteFile(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        delete a single file

        ------------------- protobuf rpc definition --------------------

        // delete a single file
        rpc DeleteFile(FileRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message FileRequest { string path = 1; }
        """
        arg = to_message(clouddrive.pb2.FileRequest, arg)
        if async_:
            return self.async_stub.DeleteFile(arg, metadata=self.metadata)
        else:
            return self.stub.DeleteFile(arg, metadata=self.metadata)

    @overload
    def DeleteFilePermanently(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def DeleteFilePermanently(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def DeleteFilePermanently(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        delete a single file permanently, only aliyundrive supports this currently

        ------------------- protobuf rpc definition --------------------

        // delete a single file permanently, only aliyundrive supports this currently
        rpc DeleteFilePermanently(FileRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message FileRequest { string path = 1; }
        """
        arg = to_message(clouddrive.pb2.FileRequest, arg)
        if async_:
            return self.async_stub.DeleteFilePermanently(arg, metadata=self.metadata)
        else:
            return self.stub.DeleteFilePermanently(arg, metadata=self.metadata)

    @overload
    def DeleteFiles(
        self, 
        arg: dict | clouddrive.pb2.MultiFileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def DeleteFiles(
        self, 
        arg: dict | clouddrive.pb2.MultiFileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def DeleteFiles(
        self, 
        arg: dict | clouddrive.pb2.MultiFileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        batch delete files

        ------------------- protobuf rpc definition --------------------

        // batch delete files
        rpc DeleteFiles(MultiFileRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message MultiFileRequest { repeated string path = 1; }
        """
        arg = to_message(clouddrive.pb2.MultiFileRequest, arg)
        if async_:
            return self.async_stub.DeleteFiles(arg, metadata=self.metadata)
        else:
            return self.stub.DeleteFiles(arg, metadata=self.metadata)

    @overload
    def DeleteFilesPermanently(
        self, 
        arg: dict | clouddrive.pb2.MultiFileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def DeleteFilesPermanently(
        self, 
        arg: dict | clouddrive.pb2.MultiFileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def DeleteFilesPermanently(
        self, 
        arg: dict | clouddrive.pb2.MultiFileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        batch delete files permanently, only aliyundrive supports this currently

        ------------------- protobuf rpc definition --------------------

        // batch delete files permanently, only aliyundrive supports this currently
        rpc DeleteFilesPermanently(MultiFileRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message MultiFileRequest { repeated string path = 1; }
        """
        arg = to_message(clouddrive.pb2.MultiFileRequest, arg)
        if async_:
            return self.async_stub.DeleteFilesPermanently(arg, metadata=self.metadata)
        else:
            return self.stub.DeleteFilesPermanently(arg, metadata=self.metadata)

    @overload
    def AddOfflineFiles(
        self, 
        arg: dict | clouddrive.pb2.AddOfflineFileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def AddOfflineFiles(
        self, 
        arg: dict | clouddrive.pb2.AddOfflineFileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def AddOfflineFiles(
        self, 
        arg: dict | clouddrive.pb2.AddOfflineFileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        add offline files by providing magnet, sha1, ..., applies only with folders
        with canOfflineDownload is true

        ------------------- protobuf rpc definition --------------------

        // add offline files by providing magnet, sha1, ..., applies only with folders
        // with canOfflineDownload is true
        rpc AddOfflineFiles(AddOfflineFileRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message AddOfflineFileRequest {
          string urls = 1;
          string toFolder = 2;
        }
        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        """
        arg = to_message(clouddrive.pb2.AddOfflineFileRequest, arg)
        if async_:
            return self.async_stub.AddOfflineFiles(arg, metadata=self.metadata)
        else:
            return self.stub.AddOfflineFiles(arg, metadata=self.metadata)

    @overload
    def RemoveOfflineFiles(
        self, 
        arg: dict | clouddrive.pb2.RemoveOfflineFilesRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def RemoveOfflineFiles(
        self, 
        arg: dict | clouddrive.pb2.RemoveOfflineFilesRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def RemoveOfflineFiles(
        self, 
        arg: dict | clouddrive.pb2.RemoveOfflineFilesRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        remove offline files by info hash

        ------------------- protobuf rpc definition --------------------

        // remove offline files by info hash
        rpc RemoveOfflineFiles(RemoveOfflineFilesRequest)
            returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message RemoveOfflineFilesRequest {
          string cloudName = 1;
          string cloudAccountId = 2;
          bool deleteFiles = 3;
          repeated string infoHashes = 4;
        }
        """
        arg = to_message(clouddrive.pb2.RemoveOfflineFilesRequest, arg)
        if async_:
            return self.async_stub.RemoveOfflineFiles(arg, metadata=self.metadata)
        else:
            return self.stub.RemoveOfflineFiles(arg, metadata=self.metadata)

    @overload
    def ListOfflineFilesByPath(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.OfflineFileListResult:
        ...
    @overload
    def ListOfflineFilesByPath(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.OfflineFileListResult]:
        ...
    def ListOfflineFilesByPath(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.OfflineFileListResult | Coroutine[Any, Any, clouddrive.pb2.OfflineFileListResult]:
        """
        list offline files

        ------------------- protobuf rpc definition --------------------

        // list offline files
        rpc ListOfflineFilesByPath(FileRequest) returns (OfflineFileListResult) {}

        ------------------- protobuf type definition -------------------

        message FileRequest { string path = 1; }
        message OfflineFile {
          string name = 1;
          uint64 size = 2;
          string url = 3;
          OfflineFileStatus status = 4;
          string infoHash = 5;
          string fileId = 6;
          uint64 add_time = 7;
          string parentId = 8;
          double percendDone = 9;
          uint64 peers = 10;
        }
        message OfflineFileListResult {
          repeated OfflineFile offlineFiles = 1;
          OfflineStatus status = 2;
        }
        message OfflineStatus {
          uint32 quota = 1;
          uint32 total = 2;
        }
        """
        arg = to_message(clouddrive.pb2.FileRequest, arg)
        if async_:
            return self.async_stub.ListOfflineFilesByPath(arg, metadata=self.metadata)
        else:
            return self.stub.ListOfflineFilesByPath(arg, metadata=self.metadata)

    @overload
    def ListAllOfflineFiles(
        self, 
        arg: dict | clouddrive.pb2.OfflineFileListAllRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.OfflineFileListAllResult:
        ...
    @overload
    def ListAllOfflineFiles(
        self, 
        arg: dict | clouddrive.pb2.OfflineFileListAllRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.OfflineFileListAllResult]:
        ...
    def ListAllOfflineFiles(
        self, 
        arg: dict | clouddrive.pb2.OfflineFileListAllRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.OfflineFileListAllResult | Coroutine[Any, Any, clouddrive.pb2.OfflineFileListAllResult]:
        """
        list all offline files of a cloud with pagination

        ------------------- protobuf rpc definition --------------------

        // list all offline files of a cloud with pagination
        rpc ListAllOfflineFiles(OfflineFileListAllRequest)
            returns (OfflineFileListAllResult) {}

        ------------------- protobuf type definition -------------------

        message OfflineFile {
          string name = 1;
          uint64 size = 2;
          string url = 3;
          OfflineFileStatus status = 4;
          string infoHash = 5;
          string fileId = 6;
          uint64 add_time = 7;
          string parentId = 8;
          double percendDone = 9;
          uint64 peers = 10;
        }
        message OfflineFileListAllRequest {
          string cloudName = 1;
          string cloudAccountId = 2;
          uint32 page = 3;
        }
        message OfflineFileListAllResult {
          uint32 pageNo = 1;
          uint32 pageRowCount = 2;
          uint32 pageCount = 3;
          uint32 totalCount = 4;
          OfflineStatus status = 5;
          repeated OfflineFile offlineFiles = 6;
        }
        message OfflineStatus {
          uint32 quota = 1;
          uint32 total = 2;
        }
        """
        arg = to_message(clouddrive.pb2.OfflineFileListAllRequest, arg)
        if async_:
            return self.async_stub.ListAllOfflineFiles(arg, metadata=self.metadata)
        else:
            return self.stub.ListAllOfflineFiles(arg, metadata=self.metadata)

    @overload
    def AddSharedLink(
        self, 
        arg: dict | clouddrive.pb2.AddSharedLinkRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def AddSharedLink(
        self, 
        arg: dict | clouddrive.pb2.AddSharedLinkRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def AddSharedLink(
        self, 
        arg: dict | clouddrive.pb2.AddSharedLinkRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        add shared link to a folder

        ------------------- protobuf rpc definition --------------------

        // add shared link to a folder
        rpc AddSharedLink(AddSharedLinkRequest) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message AddSharedLinkRequest {
          string sharedLinkUrl = 1;
          optional string sharedPassword = 2;
          string toFolder = 3;
        }
        """
        if async_:
            async def request():
                await self.async_stub.AddSharedLink(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.AddSharedLink(arg, metadata=self.metadata)
            return None

    @overload
    def GetFileDetailProperties(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileDetailProperties:
        ...
    @overload
    def GetFileDetailProperties(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileDetailProperties]:
        ...
    def GetFileDetailProperties(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileDetailProperties | Coroutine[Any, Any, clouddrive.pb2.FileDetailProperties]:
        """
        get folder properties, applies only with folders with hasDetailProperties
        is true

        ------------------- protobuf rpc definition --------------------

        // get folder properties, applies only with folders with hasDetailProperties
        // is true
        rpc GetFileDetailProperties(FileRequest) returns (FileDetailProperties) {}

        ------------------- protobuf type definition -------------------

        message FileDetailProperties {
          int64 totalFileCount = 1;
          int64 totalFolderCount = 2;
          int64 totalSize = 3;
          bool isFaved = 4;
          bool isShared = 5;
          string originalPath = 6;
        }
        message FileRequest { string path = 1; }
        """
        arg = to_message(clouddrive.pb2.FileRequest, arg)
        if async_:
            return self.async_stub.GetFileDetailProperties(arg, metadata=self.metadata)
        else:
            return self.stub.GetFileDetailProperties(arg, metadata=self.metadata)

    @overload
    def GetSpaceInfo(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.SpaceInfo:
        ...
    @overload
    def GetSpaceInfo(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.SpaceInfo]:
        ...
    def GetSpaceInfo(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.SpaceInfo | Coroutine[Any, Any, clouddrive.pb2.SpaceInfo]:
        """
        get total/free/used space of a cloud path

        ------------------- protobuf rpc definition --------------------

        // get total/free/used space of a cloud path
        rpc GetSpaceInfo(FileRequest) returns (SpaceInfo) {}

        ------------------- protobuf type definition -------------------

        message FileRequest { string path = 1; }
        message SpaceInfo {
          int64 totalSpace = 1;
          int64 usedSpace = 2;
          int64 freeSpace = 3;
        }
        """
        arg = to_message(clouddrive.pb2.FileRequest, arg)
        if async_:
            return self.async_stub.GetSpaceInfo(arg, metadata=self.metadata)
        else:
            return self.stub.GetSpaceInfo(arg, metadata=self.metadata)

    @overload
    def GetCloudMemberships(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.CloudMemberships:
        ...
    @overload
    def GetCloudMemberships(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.CloudMemberships]:
        ...
    def GetCloudMemberships(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.CloudMemberships | Coroutine[Any, Any, clouddrive.pb2.CloudMemberships]:
        """
        get cloud account memberships

        ------------------- protobuf rpc definition --------------------

        // get cloud account memberships
        rpc GetCloudMemberships(FileRequest) returns (CloudMemberships) {}

        ------------------- protobuf type definition -------------------

        message CloudMembership {
          string identity = 1;
          optional google.protobuf.Timestamp expireTime = 2;
          optional string level = 3;
        }
        message CloudMemberships { repeated CloudMembership memberships = 1; }
        message FileRequest { string path = 1; }
        """
        arg = to_message(clouddrive.pb2.FileRequest, arg)
        if async_:
            return self.async_stub.GetCloudMemberships(arg, metadata=self.metadata)
        else:
            return self.stub.GetCloudMemberships(arg, metadata=self.metadata)

    @overload
    def GetRuntimeInfo(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.RuntimeInfo:
        ...
    @overload
    def GetRuntimeInfo(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.RuntimeInfo]:
        ...
    def GetRuntimeInfo(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.RuntimeInfo | Coroutine[Any, Any, clouddrive.pb2.RuntimeInfo]:
        """
        get server runtime info

        ------------------- protobuf rpc definition --------------------

        // get server runtime info
        rpc GetRuntimeInfo(google.protobuf.Empty) returns (RuntimeInfo) {}

        ------------------- protobuf type definition -------------------

        message RuntimeInfo {
          string productName = 1;
          string productVersion = 2;
          string CloudAPIVersion = 3;
          string osInfo = 4;
        }
        """
        if async_:
            return self.async_stub.GetRuntimeInfo(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetRuntimeInfo(Empty(), metadata=self.metadata)

    @overload
    def GetRunningInfo(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.RunInfo:
        ...
    @overload
    def GetRunningInfo(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.RunInfo]:
        ...
    def GetRunningInfo(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.RunInfo | Coroutine[Any, Any, clouddrive.pb2.RunInfo]:
        """
        get server stats, including cpu/mem/uptime

        ------------------- protobuf rpc definition --------------------

        // get server stats, including cpu/mem/uptime
        rpc GetRunningInfo(google.protobuf.Empty) returns (RunInfo) {}

        ------------------- protobuf type definition -------------------

        message RunInfo {
          double cpuUsage = 1;
          uint64 memUsageKB = 2;
          double uptime = 3;
          uint64 fhTableCount = 4;
          uint64 dirCacheCount = 5;
          uint64 tempFileCount = 6;
          uint64 dbDirCacheCount = 7;
        }
        """
        if async_:
            return self.async_stub.GetRunningInfo(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetRunningInfo(Empty(), metadata=self.metadata)

    @overload
    def Logout(
        self, 
        arg: dict | clouddrive.pb2.UserLogoutRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def Logout(
        self, 
        arg: dict | clouddrive.pb2.UserLogoutRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def Logout(
        self, 
        arg: dict | clouddrive.pb2.UserLogoutRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        logout from cloudfs server

        ------------------- protobuf rpc definition --------------------

        // logout from cloudfs server
        rpc Logout(UserLogoutRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message UserLogoutRequest { bool logoutFromCloudFS = 1; }
        """
        arg = to_message(clouddrive.pb2.UserLogoutRequest, arg)
        if async_:
            return self.async_stub.Logout(arg, metadata=self.metadata)
        else:
            return self.stub.Logout(arg, metadata=self.metadata)

    @overload
    def CanAddMoreMountPoints(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def CanAddMoreMountPoints(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def CanAddMoreMountPoints(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        check if current user can add more mount point

        ------------------- protobuf rpc definition --------------------

        // check if current user can add more mount point
        rpc CanAddMoreMountPoints(google.protobuf.Empty)
            returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        """
        if async_:
            return self.async_stub.CanAddMoreMountPoints(Empty(), metadata=self.metadata)
        else:
            return self.stub.CanAddMoreMountPoints(Empty(), metadata=self.metadata)

    @overload
    def GetMountPoints(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.GetMountPointsResult:
        ...
    @overload
    def GetMountPoints(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.GetMountPointsResult]:
        ...
    def GetMountPoints(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.GetMountPointsResult | Coroutine[Any, Any, clouddrive.pb2.GetMountPointsResult]:
        """
        get all mount points

        ------------------- protobuf rpc definition --------------------

        // get all mount points
        rpc GetMountPoints(google.protobuf.Empty) returns (GetMountPointsResult) {}

        ------------------- protobuf type definition -------------------

        message GetMountPointsResult { repeated MountPoint mountPoints = 1; }
        message MountPoint {
          string mountPoint = 1;
          string sourceDir = 2;
          bool localMount = 3;
          bool readOnly = 4;
          bool autoMount = 5;
          uint32 uid = 6;
          uint32 gid = 7;
          string permissions = 8;
          bool isMounted = 9;
          string failReason = 10;
        }
        """
        if async_:
            return self.async_stub.GetMountPoints(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetMountPoints(Empty(), metadata=self.metadata)

    @overload
    def AddMountPoint(
        self, 
        arg: dict | clouddrive.pb2.MountOption, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.MountPointResult:
        ...
    @overload
    def AddMountPoint(
        self, 
        arg: dict | clouddrive.pb2.MountOption, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.MountPointResult]:
        ...
    def AddMountPoint(
        self, 
        arg: dict | clouddrive.pb2.MountOption, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.MountPointResult | Coroutine[Any, Any, clouddrive.pb2.MountPointResult]:
        """
        add a new mount point

        ------------------- protobuf rpc definition --------------------

        // add a new mount point
        rpc AddMountPoint(MountOption) returns (MountPointResult) {}

        ------------------- protobuf type definition -------------------

        message MountOption {
          string mountPoint = 1;
          string sourceDir = 2;
          bool localMount = 3;
          bool readOnly = 4;
          bool autoMount = 5;
          uint32 uid = 6;
          uint32 gid = 7;
          string permissions = 8;
          string name = 9;
        }
        message MountPointResult {
          bool success = 1;
          string failReason = 2;
        }
        """
        arg = to_message(clouddrive.pb2.MountOption, arg)
        if async_:
            return self.async_stub.AddMountPoint(arg, metadata=self.metadata)
        else:
            return self.stub.AddMountPoint(arg, metadata=self.metadata)

    @overload
    def RemoveMountPoint(
        self, 
        arg: dict | clouddrive.pb2.MountPointRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.MountPointResult:
        ...
    @overload
    def RemoveMountPoint(
        self, 
        arg: dict | clouddrive.pb2.MountPointRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.MountPointResult]:
        ...
    def RemoveMountPoint(
        self, 
        arg: dict | clouddrive.pb2.MountPointRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.MountPointResult | Coroutine[Any, Any, clouddrive.pb2.MountPointResult]:
        """
        remove a mountpoint

        ------------------- protobuf rpc definition --------------------

        // remove a mountpoint
        rpc RemoveMountPoint(MountPointRequest) returns (MountPointResult) {}

        ------------------- protobuf type definition -------------------

        message MountPointRequest { string MountPoint = 1; }
        message MountPointResult {
          bool success = 1;
          string failReason = 2;
        }
        """
        arg = to_message(clouddrive.pb2.MountPointRequest, arg)
        if async_:
            return self.async_stub.RemoveMountPoint(arg, metadata=self.metadata)
        else:
            return self.stub.RemoveMountPoint(arg, metadata=self.metadata)

    @overload
    def Mount(
        self, 
        arg: dict | clouddrive.pb2.MountPointRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.MountPointResult:
        ...
    @overload
    def Mount(
        self, 
        arg: dict | clouddrive.pb2.MountPointRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.MountPointResult]:
        ...
    def Mount(
        self, 
        arg: dict | clouddrive.pb2.MountPointRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.MountPointResult | Coroutine[Any, Any, clouddrive.pb2.MountPointResult]:
        """
        mount a mount point

        ------------------- protobuf rpc definition --------------------

        // mount a mount point
        rpc Mount(MountPointRequest) returns (MountPointResult) {}

        ------------------- protobuf type definition -------------------

        message MountPointRequest { string MountPoint = 1; }
        message MountPointResult {
          bool success = 1;
          string failReason = 2;
        }
        """
        arg = to_message(clouddrive.pb2.MountPointRequest, arg)
        if async_:
            return self.async_stub.Mount(arg, metadata=self.metadata)
        else:
            return self.stub.Mount(arg, metadata=self.metadata)

    @overload
    def Unmount(
        self, 
        arg: dict | clouddrive.pb2.MountPointRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.MountPointResult:
        ...
    @overload
    def Unmount(
        self, 
        arg: dict | clouddrive.pb2.MountPointRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.MountPointResult]:
        ...
    def Unmount(
        self, 
        arg: dict | clouddrive.pb2.MountPointRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.MountPointResult | Coroutine[Any, Any, clouddrive.pb2.MountPointResult]:
        """
        unmount a mount point

        ------------------- protobuf rpc definition --------------------

        // unmount a mount point
        rpc Unmount(MountPointRequest) returns (MountPointResult) {}

        ------------------- protobuf type definition -------------------

        message MountPointRequest { string MountPoint = 1; }
        message MountPointResult {
          bool success = 1;
          string failReason = 2;
        }
        """
        arg = to_message(clouddrive.pb2.MountPointRequest, arg)
        if async_:
            return self.async_stub.Unmount(arg, metadata=self.metadata)
        else:
            return self.stub.Unmount(arg, metadata=self.metadata)

    @overload
    def UpdateMountPoint(
        self, 
        arg: dict | clouddrive.pb2.UpdateMountPointRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.MountPointResult:
        ...
    @overload
    def UpdateMountPoint(
        self, 
        arg: dict | clouddrive.pb2.UpdateMountPointRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.MountPointResult]:
        ...
    def UpdateMountPoint(
        self, 
        arg: dict | clouddrive.pb2.UpdateMountPointRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.MountPointResult | Coroutine[Any, Any, clouddrive.pb2.MountPointResult]:
        """
        change mount point settings

        ------------------- protobuf rpc definition --------------------

        // change mount point settings
        rpc UpdateMountPoint(UpdateMountPointRequest) returns (MountPointResult) {}

        ------------------- protobuf type definition -------------------

        message MountOption {
          string mountPoint = 1;
          string sourceDir = 2;
          bool localMount = 3;
          bool readOnly = 4;
          bool autoMount = 5;
          uint32 uid = 6;
          uint32 gid = 7;
          string permissions = 8;
          string name = 9;
        }
        message MountPointResult {
          bool success = 1;
          string failReason = 2;
        }
        message UpdateMountPointRequest {
          string mountPoint = 1;
          MountOption newMountOption = 2;
        }
        """
        arg = to_message(clouddrive.pb2.UpdateMountPointRequest, arg)
        if async_:
            return self.async_stub.UpdateMountPoint(arg, metadata=self.metadata)
        else:
            return self.stub.UpdateMountPoint(arg, metadata=self.metadata)

    @overload
    def GetAvailableDriveLetters(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.GetAvailableDriveLettersResult:
        ...
    @overload
    def GetAvailableDriveLetters(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.GetAvailableDriveLettersResult]:
        ...
    def GetAvailableDriveLetters(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.GetAvailableDriveLettersResult | Coroutine[Any, Any, clouddrive.pb2.GetAvailableDriveLettersResult]:
        """
        get all unused drive letters from server's local storage, applies to
        windows only

        ------------------- protobuf rpc definition --------------------

        // get all unused drive letters from server's local storage, applies to
        // windows only
        rpc GetAvailableDriveLetters(google.protobuf.Empty)
            returns (GetAvailableDriveLettersResult) {}

        ------------------- protobuf type definition -------------------

        message GetAvailableDriveLettersResult { repeated string driveLetters = 1; }
        """
        if async_:
            return self.async_stub.GetAvailableDriveLetters(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetAvailableDriveLetters(Empty(), metadata=self.metadata)

    @overload
    def HasDriveLetters(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.HasDriveLettersResult:
        ...
    @overload
    def HasDriveLetters(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.HasDriveLettersResult]:
        ...
    def HasDriveLetters(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.HasDriveLettersResult | Coroutine[Any, Any, clouddrive.pb2.HasDriveLettersResult]:
        """
        check if server has driver letters, returns true only on windows

        ------------------- protobuf rpc definition --------------------

        // check if server has driver letters, returns true only on windows
        rpc HasDriveLetters(google.protobuf.Empty) returns (HasDriveLettersResult) {}

        ------------------- protobuf type definition -------------------

        message HasDriveLettersResult { bool hasDriveLetters = 1; }
        """
        if async_:
            return self.async_stub.HasDriveLetters(Empty(), metadata=self.metadata)
        else:
            return self.stub.HasDriveLetters(Empty(), metadata=self.metadata)

    @overload
    def LocalGetSubFiles(
        self, 
        arg: dict | clouddrive.pb2.LocalGetSubFilesRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> Iterable[clouddrive.pb2.LocalGetSubFilesResult]:
        ...
    @overload
    def LocalGetSubFiles(
        self, 
        arg: dict | clouddrive.pb2.LocalGetSubFilesRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Iterable[clouddrive.pb2.LocalGetSubFilesResult]]:
        ...
    def LocalGetSubFiles(
        self, 
        arg: dict | clouddrive.pb2.LocalGetSubFilesRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Iterable[clouddrive.pb2.LocalGetSubFilesResult] | Coroutine[Any, Any, Iterable[clouddrive.pb2.LocalGetSubFilesResult]]:
        """
        get subfiles of a local path, used for adding mountpoint from web ui

        ------------------- protobuf rpc definition --------------------

        // get subfiles of a local path, used for adding mountpoint from web ui
        rpc LocalGetSubFiles(LocalGetSubFilesRequest)
            returns (stream LocalGetSubFilesResult) {}

        ------------------- protobuf type definition -------------------

        message LocalGetSubFilesRequest {
          string parentFolder = 1;
          bool folderOnly = 2;
          bool includeCloudDrive = 3;
          bool includeAvailableDrive = 4;
        }
        message LocalGetSubFilesResult { repeated string subFiles = 1; }
        """
        arg = to_message(clouddrive.pb2.LocalGetSubFilesRequest, arg)
        if async_:
            return self.async_stub.LocalGetSubFiles(arg, metadata=self.metadata)
        else:
            return self.stub.LocalGetSubFiles(arg, metadata=self.metadata)

    @overload
    def GetAllTasksCount(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.GetAllTasksCountResult:
        ...
    @overload
    def GetAllTasksCount(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.GetAllTasksCountResult]:
        ...
    def GetAllTasksCount(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.GetAllTasksCountResult | Coroutine[Any, Any, clouddrive.pb2.GetAllTasksCountResult]:
        """
        get all transfer tasks' count

        ------------------- protobuf rpc definition --------------------

        // get all transfer tasks' count
        rpc GetAllTasksCount(google.protobuf.Empty) returns (GetAllTasksCountResult) {
        }

        ------------------- protobuf type definition -------------------

        message GetAllTasksCountResult {
          uint32 downloadCount = 1;
          uint32 uploadCount = 2;
          PushMessage pushMessage = 3;
          bool hasUpdate = 4;
          repeated UploadFileInfo uploadFileStatusChanges = 5; //upload file status changed
        }
        message PushMessage { string clouddriveVersion = 1; }
        message UploadFileInfo {
          string key = 1;
          string destPath = 2;
          uint64 size = 3;
          uint64 transferedBytes = 4;
          string status = 5;
          string errorMessage = 6;
        }
        """
        if async_:
            return self.async_stub.GetAllTasksCount(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetAllTasksCount(Empty(), metadata=self.metadata)

    @overload
    def GetDownloadFileCount(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.GetDownloadFileCountResult:
        ...
    @overload
    def GetDownloadFileCount(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.GetDownloadFileCountResult]:
        ...
    def GetDownloadFileCount(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.GetDownloadFileCountResult | Coroutine[Any, Any, clouddrive.pb2.GetDownloadFileCountResult]:
        """
        get download tasks' count

        ------------------- protobuf rpc definition --------------------

        // get download tasks' count
        rpc GetDownloadFileCount(google.protobuf.Empty)
            returns (GetDownloadFileCountResult) {}

        ------------------- protobuf type definition -------------------

        message GetDownloadFileCountResult { uint32 fileCount = 1; }
        """
        if async_:
            return self.async_stub.GetDownloadFileCount(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetDownloadFileCount(Empty(), metadata=self.metadata)

    @overload
    def GetDownloadFileList(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.GetDownloadFileListResult:
        ...
    @overload
    def GetDownloadFileList(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.GetDownloadFileListResult]:
        ...
    def GetDownloadFileList(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.GetDownloadFileListResult | Coroutine[Any, Any, clouddrive.pb2.GetDownloadFileListResult]:
        """
        get all download tasks

        ------------------- protobuf rpc definition --------------------

        // get all download tasks
        rpc GetDownloadFileList(google.protobuf.Empty)
            returns (GetDownloadFileListResult) {}

        ------------------- protobuf type definition -------------------

        message DownloadFileInfo {
          string filePath = 1;
          uint64 fileLength = 2;
          uint64 totalBufferUsed = 3;
          uint32 downloadThreadCount = 4;
          repeated string process = 5;
          string detailDownloadInfo = 6;
          optional string lastDownloadError = 7;
        }
        message GetDownloadFileListResult {
          double globalBytesPerSecond = 1;
          repeated DownloadFileInfo downloadFiles = 4;
        }
        """
        if async_:
            return self.async_stub.GetDownloadFileList(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetDownloadFileList(Empty(), metadata=self.metadata)

    @overload
    def GetUploadFileCount(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.GetUploadFileCountResult:
        ...
    @overload
    def GetUploadFileCount(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.GetUploadFileCountResult]:
        ...
    def GetUploadFileCount(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.GetUploadFileCountResult | Coroutine[Any, Any, clouddrive.pb2.GetUploadFileCountResult]:
        """
        get all upload tasks' count

        ------------------- protobuf rpc definition --------------------

        // get all upload tasks' count
        rpc GetUploadFileCount(google.protobuf.Empty)
            returns (GetUploadFileCountResult) {}

        ------------------- protobuf type definition -------------------

        message GetUploadFileCountResult { uint32 fileCount = 1; }
        """
        if async_:
            return self.async_stub.GetUploadFileCount(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetUploadFileCount(Empty(), metadata=self.metadata)

    @overload
    def GetUploadFileList(
        self, 
        arg: dict | clouddrive.pb2.GetUploadFileListRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.GetUploadFileListResult:
        ...
    @overload
    def GetUploadFileList(
        self, 
        arg: dict | clouddrive.pb2.GetUploadFileListRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.GetUploadFileListResult]:
        ...
    def GetUploadFileList(
        self, 
        arg: dict | clouddrive.pb2.GetUploadFileListRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.GetUploadFileListResult | Coroutine[Any, Any, clouddrive.pb2.GetUploadFileListResult]:
        """
        get upload tasks, paged by providing page number and items per page and
        file name filter

        ------------------- protobuf rpc definition --------------------

        // get upload tasks, paged by providing page number and items per page and
        // file name filter
        rpc GetUploadFileList(GetUploadFileListRequest)
            returns (GetUploadFileListResult) {}

        ------------------- protobuf type definition -------------------

        message GetUploadFileListRequest {
          bool getAll = 1;
          uint32 itemsPerPage = 2;
          uint32 pageNumber = 3;
          string filter = 4;
        }
        message GetUploadFileListResult {
          uint32 totalCount = 1;
          repeated UploadFileInfo uploadFiles = 2;
          double globalBytesPerSecond = 3;
        }
        message UploadFileInfo {
          string key = 1;
          string destPath = 2;
          uint64 size = 3;
          uint64 transferedBytes = 4;
          string status = 5;
          string errorMessage = 6;
        }
        """
        arg = to_message(clouddrive.pb2.GetUploadFileListRequest, arg)
        if async_:
            return self.async_stub.GetUploadFileList(arg, metadata=self.metadata)
        else:
            return self.stub.GetUploadFileList(arg, metadata=self.metadata)

    @overload
    def CancelAllUploadFiles(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def CancelAllUploadFiles(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def CancelAllUploadFiles(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        cancel all upload tasks

        ------------------- protobuf rpc definition --------------------

        // cancel all upload tasks
        rpc CancelAllUploadFiles(google.protobuf.Empty)
            returns (google.protobuf.Empty) {}
        """
        if async_:
            async def request():
                await self.async_stub.CancelAllUploadFiles(Empty(), metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.CancelAllUploadFiles(Empty(), metadata=self.metadata)
            return None

    @overload
    def CancelUploadFiles(
        self, 
        arg: dict | clouddrive.pb2.MultpleUploadFileKeyRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def CancelUploadFiles(
        self, 
        arg: dict | clouddrive.pb2.MultpleUploadFileKeyRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def CancelUploadFiles(
        self, 
        arg: dict | clouddrive.pb2.MultpleUploadFileKeyRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        cancel selected upload tasks

        ------------------- protobuf rpc definition --------------------

        // cancel selected upload tasks
        rpc CancelUploadFiles(MultpleUploadFileKeyRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message MultpleUploadFileKeyRequest { repeated string keys = 1; }
        """
        if async_:
            async def request():
                await self.async_stub.CancelUploadFiles(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.CancelUploadFiles(arg, metadata=self.metadata)
            return None

    @overload
    def PauseAllUploadFiles(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def PauseAllUploadFiles(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def PauseAllUploadFiles(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        pause all upload tasks

        ------------------- protobuf rpc definition --------------------

        // pause all upload tasks
        rpc PauseAllUploadFiles(google.protobuf.Empty)
            returns (google.protobuf.Empty) {}
        """
        if async_:
            async def request():
                await self.async_stub.PauseAllUploadFiles(Empty(), metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.PauseAllUploadFiles(Empty(), metadata=self.metadata)
            return None

    @overload
    def PauseUploadFiles(
        self, 
        arg: dict | clouddrive.pb2.MultpleUploadFileKeyRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def PauseUploadFiles(
        self, 
        arg: dict | clouddrive.pb2.MultpleUploadFileKeyRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def PauseUploadFiles(
        self, 
        arg: dict | clouddrive.pb2.MultpleUploadFileKeyRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        pause selected upload tasks

        ------------------- protobuf rpc definition --------------------

        // pause selected upload tasks
        rpc PauseUploadFiles(MultpleUploadFileKeyRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message MultpleUploadFileKeyRequest { repeated string keys = 1; }
        """
        if async_:
            async def request():
                await self.async_stub.PauseUploadFiles(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.PauseUploadFiles(arg, metadata=self.metadata)
            return None

    @overload
    def ResumeAllUploadFiles(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def ResumeAllUploadFiles(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def ResumeAllUploadFiles(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        resume all upload tasks

        ------------------- protobuf rpc definition --------------------

        // resume all upload tasks
        rpc ResumeAllUploadFiles(google.protobuf.Empty)
            returns (google.protobuf.Empty) {}
        """
        if async_:
            async def request():
                await self.async_stub.ResumeAllUploadFiles(Empty(), metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.ResumeAllUploadFiles(Empty(), metadata=self.metadata)
            return None

    @overload
    def ResumeUploadFiles(
        self, 
        arg: dict | clouddrive.pb2.MultpleUploadFileKeyRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def ResumeUploadFiles(
        self, 
        arg: dict | clouddrive.pb2.MultpleUploadFileKeyRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def ResumeUploadFiles(
        self, 
        arg: dict | clouddrive.pb2.MultpleUploadFileKeyRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        resume selected upload tasks

        ------------------- protobuf rpc definition --------------------

        // resume selected upload tasks
        rpc ResumeUploadFiles(MultpleUploadFileKeyRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message MultpleUploadFileKeyRequest { repeated string keys = 1; }
        """
        if async_:
            async def request():
                await self.async_stub.ResumeUploadFiles(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.ResumeUploadFiles(arg, metadata=self.metadata)
            return None

    @overload
    def CanAddMoreCloudApis(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def CanAddMoreCloudApis(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def CanAddMoreCloudApis(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        check if current user can add more cloud apis

        ------------------- protobuf rpc definition --------------------

        // check if current user can add more cloud apis
        rpc CanAddMoreCloudApis(google.protobuf.Empty) returns (FileOperationResult) {
        }

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        """
        if async_:
            return self.async_stub.CanAddMoreCloudApis(Empty(), metadata=self.metadata)
        else:
            return self.stub.CanAddMoreCloudApis(Empty(), metadata=self.metadata)

    @overload
    def APILogin115Editthiscookie(
        self, 
        arg: dict | clouddrive.pb2.Login115EditthiscookieRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.APILoginResult:
        ...
    @overload
    def APILogin115Editthiscookie(
        self, 
        arg: dict | clouddrive.pb2.Login115EditthiscookieRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        ...
    def APILogin115Editthiscookie(
        self, 
        arg: dict | clouddrive.pb2.Login115EditthiscookieRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.APILoginResult | Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        """
        add 115 cloud with editthiscookie

        ------------------- protobuf rpc definition --------------------

        // add 115 cloud with editthiscookie
        rpc APILogin115Editthiscookie(Login115EditthiscookieRequest)
            returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message Login115EditthiscookieRequest { string editThiscookieString = 1; }
        """
        arg = to_message(clouddrive.pb2.Login115EditthiscookieRequest, arg)
        if async_:
            return self.async_stub.APILogin115Editthiscookie(arg, metadata=self.metadata)
        else:
            return self.stub.APILogin115Editthiscookie(arg, metadata=self.metadata)

    @overload
    def APILogin115QRCode(
        self, 
        arg: dict | clouddrive.pb2.Login115QrCodeRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> Iterable[clouddrive.pb2.QRCodeScanMessage]:
        ...
    @overload
    def APILogin115QRCode(
        self, 
        arg: dict | clouddrive.pb2.Login115QrCodeRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Iterable[clouddrive.pb2.QRCodeScanMessage]]:
        ...
    def APILogin115QRCode(
        self, 
        arg: dict | clouddrive.pb2.Login115QrCodeRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Iterable[clouddrive.pb2.QRCodeScanMessage] | Coroutine[Any, Any, Iterable[clouddrive.pb2.QRCodeScanMessage]]:
        """
        add 115 cloud with qr scanning

        ------------------- protobuf rpc definition --------------------

        // add 115 cloud with qr scanning
        rpc APILogin115QRCode(Login115QrCodeRequest)
            returns (stream QRCodeScanMessage) {}

        ------------------- protobuf type definition -------------------

        message Login115QrCodeRequest { optional string platformString = 1; }
        message QRCodeScanMessage {
          QRCodeScanMessageType messageType = 1;
          string message = 2;
        }
        enum QRCodeScanMessageType {
          SHOW_IMAGE = 0;
          SHOW_IMAGE_CONTENT = 1;
          CHANGE_STATUS = 2;
          CLOSE = 3;
          ERROR = 4;
        }
        """
        arg = to_message(clouddrive.pb2.Login115QrCodeRequest, arg)
        if async_:
            return self.async_stub.APILogin115QRCode(arg, metadata=self.metadata)
        else:
            return self.stub.APILogin115QRCode(arg, metadata=self.metadata)

    @overload
    def APILoginAliyundriveOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginAliyundriveOAuthRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.APILoginResult:
        ...
    @overload
    def APILoginAliyundriveOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginAliyundriveOAuthRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        ...
    def APILoginAliyundriveOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginAliyundriveOAuthRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.APILoginResult | Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        """
        add AliyunDriveOpen with OAuth result

        ------------------- protobuf rpc definition --------------------

        // add AliyunDriveOpen with OAuth result
        rpc APILoginAliyundriveOAuth(LoginAliyundriveOAuthRequest)
            returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message LoginAliyundriveOAuthRequest {
          string refresh_token = 1;
          string access_token = 2;
          uint64 expires_in = 3;
        }
        """
        arg = to_message(clouddrive.pb2.LoginAliyundriveOAuthRequest, arg)
        if async_:
            return self.async_stub.APILoginAliyundriveOAuth(arg, metadata=self.metadata)
        else:
            return self.stub.APILoginAliyundriveOAuth(arg, metadata=self.metadata)

    @overload
    def APILoginAliyundriveRefreshtoken(
        self, 
        arg: dict | clouddrive.pb2.LoginAliyundriveRefreshtokenRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.APILoginResult:
        ...
    @overload
    def APILoginAliyundriveRefreshtoken(
        self, 
        arg: dict | clouddrive.pb2.LoginAliyundriveRefreshtokenRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        ...
    def APILoginAliyundriveRefreshtoken(
        self, 
        arg: dict | clouddrive.pb2.LoginAliyundriveRefreshtokenRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.APILoginResult | Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        """
        add AliyunDrive with refresh token

        ------------------- protobuf rpc definition --------------------

        // add AliyunDrive with refresh token
        rpc APILoginAliyundriveRefreshtoken(LoginAliyundriveRefreshtokenRequest)
            returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message LoginAliyundriveRefreshtokenRequest {
          string refreshToken = 1;
          bool useOpenAPI = 2;
        }
        """
        arg = to_message(clouddrive.pb2.LoginAliyundriveRefreshtokenRequest, arg)
        if async_:
            return self.async_stub.APILoginAliyundriveRefreshtoken(arg, metadata=self.metadata)
        else:
            return self.stub.APILoginAliyundriveRefreshtoken(arg, metadata=self.metadata)

    @overload
    def APILoginAliyunDriveQRCode(
        self, 
        arg: dict | clouddrive.pb2.LoginAliyundriveQRCodeRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> Iterable[clouddrive.pb2.QRCodeScanMessage]:
        ...
    @overload
    def APILoginAliyunDriveQRCode(
        self, 
        arg: dict | clouddrive.pb2.LoginAliyundriveQRCodeRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Iterable[clouddrive.pb2.QRCodeScanMessage]]:
        ...
    def APILoginAliyunDriveQRCode(
        self, 
        arg: dict | clouddrive.pb2.LoginAliyundriveQRCodeRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Iterable[clouddrive.pb2.QRCodeScanMessage] | Coroutine[Any, Any, Iterable[clouddrive.pb2.QRCodeScanMessage]]:
        """
        add AliyunDrive with qr scanning

        ------------------- protobuf rpc definition --------------------

        // add AliyunDrive with qr scanning
        rpc APILoginAliyunDriveQRCode(LoginAliyundriveQRCodeRequest)
            returns (stream QRCodeScanMessage) {}

        ------------------- protobuf type definition -------------------

        message LoginAliyundriveQRCodeRequest { bool useOpenAPI = 1; }
        message QRCodeScanMessage {
          QRCodeScanMessageType messageType = 1;
          string message = 2;
        }
        enum QRCodeScanMessageType {
          SHOW_IMAGE = 0;
          SHOW_IMAGE_CONTENT = 1;
          CHANGE_STATUS = 2;
          CLOSE = 3;
          ERROR = 4;
        }
        """
        arg = to_message(clouddrive.pb2.LoginAliyundriveQRCodeRequest, arg)
        if async_:
            return self.async_stub.APILoginAliyunDriveQRCode(arg, metadata=self.metadata)
        else:
            return self.stub.APILoginAliyunDriveQRCode(arg, metadata=self.metadata)

    @overload
    def APILoginBaiduPanOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginBaiduPanOAuthRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.APILoginResult:
        ...
    @overload
    def APILoginBaiduPanOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginBaiduPanOAuthRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        ...
    def APILoginBaiduPanOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginBaiduPanOAuthRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.APILoginResult | Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        """
        add BaiduPan with OAuth result

        ------------------- protobuf rpc definition --------------------

        // add BaiduPan with OAuth result
        rpc APILoginBaiduPanOAuth(LoginBaiduPanOAuthRequest)
            returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message LoginBaiduPanOAuthRequest {
          string refresh_token = 1;
          string access_token = 2;
          uint64 expires_in = 3;
        }
        """
        arg = to_message(clouddrive.pb2.LoginBaiduPanOAuthRequest, arg)
        if async_:
            return self.async_stub.APILoginBaiduPanOAuth(arg, metadata=self.metadata)
        else:
            return self.stub.APILoginBaiduPanOAuth(arg, metadata=self.metadata)

    @overload
    def APILoginOneDriveOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginOneDriveOAuthRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.APILoginResult:
        ...
    @overload
    def APILoginOneDriveOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginOneDriveOAuthRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        ...
    def APILoginOneDriveOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginOneDriveOAuthRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.APILoginResult | Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        """
        add OneDrive with OAuth result

        ------------------- protobuf rpc definition --------------------

        // add OneDrive with OAuth result
        rpc APILoginOneDriveOAuth(LoginOneDriveOAuthRequest)
            returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message LoginOneDriveOAuthRequest {
          string refresh_token = 1;
          string access_token = 2;
          uint64 expires_in = 3;
        }
        """
        arg = to_message(clouddrive.pb2.LoginOneDriveOAuthRequest, arg)
        if async_:
            return self.async_stub.APILoginOneDriveOAuth(arg, metadata=self.metadata)
        else:
            return self.stub.APILoginOneDriveOAuth(arg, metadata=self.metadata)

    @overload
    def ApiLoginGoogleDriveOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginGoogleDriveOAuthRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.APILoginResult:
        ...
    @overload
    def ApiLoginGoogleDriveOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginGoogleDriveOAuthRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        ...
    def ApiLoginGoogleDriveOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginGoogleDriveOAuthRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.APILoginResult | Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        """
        add Google Drive with OAuth result

        ------------------- protobuf rpc definition --------------------

        // add Google Drive with OAuth result
        rpc ApiLoginGoogleDriveOAuth(LoginGoogleDriveOAuthRequest)
            returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message LoginGoogleDriveOAuthRequest {
          string refresh_token = 1;
          string access_token = 2;
          uint64 expires_in = 3;
        }
        """
        arg = to_message(clouddrive.pb2.LoginGoogleDriveOAuthRequest, arg)
        if async_:
            return self.async_stub.ApiLoginGoogleDriveOAuth(arg, metadata=self.metadata)
        else:
            return self.stub.ApiLoginGoogleDriveOAuth(arg, metadata=self.metadata)

    @overload
    def ApiLoginGoogleDriveRefreshToken(
        self, 
        arg: dict | clouddrive.pb2.LoginGoogleDriveRefreshTokenRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.APILoginResult:
        ...
    @overload
    def ApiLoginGoogleDriveRefreshToken(
        self, 
        arg: dict | clouddrive.pb2.LoginGoogleDriveRefreshTokenRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        ...
    def ApiLoginGoogleDriveRefreshToken(
        self, 
        arg: dict | clouddrive.pb2.LoginGoogleDriveRefreshTokenRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.APILoginResult | Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        """
        add Google Drive with refresh token

        ------------------- protobuf rpc definition --------------------

        // add Google Drive with refresh token
        rpc ApiLoginGoogleDriveRefreshToken(LoginGoogleDriveRefreshTokenRequest)
            returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message LoginGoogleDriveRefreshTokenRequest {
          string client_id = 1;
          string client_secret = 2;
          string refresh_token = 3;
        }
        """
        arg = to_message(clouddrive.pb2.LoginGoogleDriveRefreshTokenRequest, arg)
        if async_:
            return self.async_stub.ApiLoginGoogleDriveRefreshToken(arg, metadata=self.metadata)
        else:
            return self.stub.ApiLoginGoogleDriveRefreshToken(arg, metadata=self.metadata)

    @overload
    def ApiLoginXunleiOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginXunleiOAuthRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.APILoginResult:
        ...
    @overload
    def ApiLoginXunleiOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginXunleiOAuthRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        ...
    def ApiLoginXunleiOAuth(
        self, 
        arg: dict | clouddrive.pb2.LoginXunleiOAuthRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.APILoginResult | Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        """
        add Xunlei Drive with OAuth result

        ------------------- protobuf rpc definition --------------------

        // add Xunlei Drive with OAuth result
        rpc ApiLoginXunleiOAuth(LoginXunleiOAuthRequest) returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message LoginXunleiOAuthRequest {
          string refresh_token = 1;
          string access_token = 2;
          uint64 expires_in = 3;
        }
        """
        arg = to_message(clouddrive.pb2.LoginXunleiOAuthRequest, arg)
        if async_:
            return self.async_stub.ApiLoginXunleiOAuth(arg, metadata=self.metadata)
        else:
            return self.stub.ApiLoginXunleiOAuth(arg, metadata=self.metadata)

    @overload
    def ApiLogin123panOAuth(
        self, 
        arg: dict | clouddrive.pb2.Login123panOAuthRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.APILoginResult:
        ...
    @overload
    def ApiLogin123panOAuth(
        self, 
        arg: dict | clouddrive.pb2.Login123panOAuthRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        ...
    def ApiLogin123panOAuth(
        self, 
        arg: dict | clouddrive.pb2.Login123panOAuthRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.APILoginResult | Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        """
        add 123 cloud with client id and client secret

        ------------------- protobuf rpc definition --------------------

        // add 123 cloud with client id and client secret
        rpc ApiLogin123panOAuth(Login123panOAuthRequest) returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message Login123panOAuthRequest {
          string refresh_token = 1;
          string access_token = 2;
          uint64 expires_in = 3;
        }
        """
        arg = to_message(clouddrive.pb2.Login123panOAuthRequest, arg)
        if async_:
            return self.async_stub.ApiLogin123panOAuth(arg, metadata=self.metadata)
        else:
            return self.stub.ApiLogin123panOAuth(arg, metadata=self.metadata)

    @overload
    def APILogin189QRCode(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> Iterable[clouddrive.pb2.QRCodeScanMessage]:
        ...
    @overload
    def APILogin189QRCode(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Iterable[clouddrive.pb2.QRCodeScanMessage]]:
        ...
    def APILogin189QRCode(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Iterable[clouddrive.pb2.QRCodeScanMessage] | Coroutine[Any, Any, Iterable[clouddrive.pb2.QRCodeScanMessage]]:
        """
        add 189 cloud with qr scanning

        ------------------- protobuf rpc definition --------------------

        // add 189 cloud with qr scanning
        rpc APILogin189QRCode(google.protobuf.Empty)
            returns (stream QRCodeScanMessage) {}

        ------------------- protobuf type definition -------------------

        message QRCodeScanMessage {
          QRCodeScanMessageType messageType = 1;
          string message = 2;
        }
        enum QRCodeScanMessageType {
          SHOW_IMAGE = 0;
          SHOW_IMAGE_CONTENT = 1;
          CHANGE_STATUS = 2;
          CLOSE = 3;
          ERROR = 4;
        }
        """
        if async_:
            return self.async_stub.APILogin189QRCode(Empty(), metadata=self.metadata)
        else:
            return self.stub.APILogin189QRCode(Empty(), metadata=self.metadata)

    @overload
    def APILoginWebDav(
        self, 
        arg: dict | clouddrive.pb2.LoginWebDavRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.APILoginResult:
        ...
    @overload
    def APILoginWebDav(
        self, 
        arg: dict | clouddrive.pb2.LoginWebDavRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        ...
    def APILoginWebDav(
        self, 
        arg: dict | clouddrive.pb2.LoginWebDavRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.APILoginResult | Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        """
        add PikPak cloud with username and password
        rpc APILoginPikPak(UserLoginRequest) returns (APILoginResult) {}
        add webdav

        ------------------- protobuf rpc definition --------------------

        // add PikPak cloud with username and password
        // rpc APILoginPikPak(UserLoginRequest) returns (APILoginResult) {}
        // add webdav
        rpc APILoginWebDav(LoginWebDavRequest) returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message LoginWebDavRequest {
          string serverUrl = 1;
          string userName = 2;
          string password = 3;
        }
        """
        arg = to_message(clouddrive.pb2.LoginWebDavRequest, arg)
        if async_:
            return self.async_stub.APILoginWebDav(arg, metadata=self.metadata)
        else:
            return self.stub.APILoginWebDav(arg, metadata=self.metadata)

    @overload
    def APIAddLocalFolder(
        self, 
        arg: dict | clouddrive.pb2.AddLocalFolderRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.APILoginResult:
        ...
    @overload
    def APIAddLocalFolder(
        self, 
        arg: dict | clouddrive.pb2.AddLocalFolderRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        ...
    def APIAddLocalFolder(
        self, 
        arg: dict | clouddrive.pb2.AddLocalFolderRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.APILoginResult | Coroutine[Any, Any, clouddrive.pb2.APILoginResult]:
        """
        add local folder

        ------------------- protobuf rpc definition --------------------

        // add local folder
        rpc APIAddLocalFolder(AddLocalFolderRequest) returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message AddLocalFolderRequest { string localFolderPath = 1; }
        """
        arg = to_message(clouddrive.pb2.AddLocalFolderRequest, arg)
        if async_:
            return self.async_stub.APIAddLocalFolder(arg, metadata=self.metadata)
        else:
            return self.stub.APIAddLocalFolder(arg, metadata=self.metadata)

    @overload
    def RemoveCloudAPI(
        self, 
        arg: dict | clouddrive.pb2.RemoveCloudAPIRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def RemoveCloudAPI(
        self, 
        arg: dict | clouddrive.pb2.RemoveCloudAPIRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def RemoveCloudAPI(
        self, 
        arg: dict | clouddrive.pb2.RemoveCloudAPIRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        remove a cloud

        ------------------- protobuf rpc definition --------------------

        // remove a cloud
        rpc RemoveCloudAPI(RemoveCloudAPIRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        message RemoveCloudAPIRequest {
          string cloudName = 1;
          string userName = 2;
          bool permanentRemove = 3;
        }
        """
        arg = to_message(clouddrive.pb2.RemoveCloudAPIRequest, arg)
        if async_:
            return self.async_stub.RemoveCloudAPI(arg, metadata=self.metadata)
        else:
            return self.stub.RemoveCloudAPI(arg, metadata=self.metadata)

    @overload
    def GetAllCloudApis(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.CloudAPIList:
        ...
    @overload
    def GetAllCloudApis(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.CloudAPIList]:
        ...
    def GetAllCloudApis(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.CloudAPIList | Coroutine[Any, Any, clouddrive.pb2.CloudAPIList]:
        """
        get all cloud apis

        ------------------- protobuf rpc definition --------------------

        // get all cloud apis
        rpc GetAllCloudApis(google.protobuf.Empty) returns (CloudAPIList) {}

        ------------------- protobuf type definition -------------------

        message CloudAPI {
          string name = 1;
          string userName = 2;
          string nickName = 3;
          bool isLocked = 4; // isLocked means the cloudAPI is set to can't open files,
                             // due to user's membership issue
          bool supportMultiThreadUploading = 5;
          bool supportQpsLimit = 6;
          bool isCloudEventListenerRunning = 7;
        }
        message CloudAPIList { repeated CloudAPI apis = 1; }
        """
        if async_:
            return self.async_stub.GetAllCloudApis(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetAllCloudApis(Empty(), metadata=self.metadata)

    @overload
    def GetCloudAPIConfig(
        self, 
        arg: dict | clouddrive.pb2.GetCloudAPIConfigRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.CloudAPIConfig:
        ...
    @overload
    def GetCloudAPIConfig(
        self, 
        arg: dict | clouddrive.pb2.GetCloudAPIConfigRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.CloudAPIConfig]:
        ...
    def GetCloudAPIConfig(
        self, 
        arg: dict | clouddrive.pb2.GetCloudAPIConfigRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.CloudAPIConfig | Coroutine[Any, Any, clouddrive.pb2.CloudAPIConfig]:
        """
        get CloudAPI configuration

        ------------------- protobuf rpc definition --------------------

        // get CloudAPI configuration
        rpc GetCloudAPIConfig(GetCloudAPIConfigRequest) returns (CloudAPIConfig) {}

        ------------------- protobuf type definition -------------------

        message CloudAPIConfig {
          uint32 maxDownloadThreads = 1;
          uint64 minReadLengthKB = 2;
          uint64 maxReadLengthKB = 3;
          uint64 defaultReadLengthKB = 4;
          uint64 maxBufferPoolSizeMB = 5;
          double maxQueriesPerSecond = 6;
          bool forceIpv4 = 7;
          optional ProxyInfo apiProxy = 8;
          optional ProxyInfo dataProxy = 9;
          optional string customUserAgent = 10;
          optional uint32 maxUploadThreads = 11;
        }
        message GetCloudAPIConfigRequest {
          string cloudName = 1;
          string userName = 2;
        }
        message ProxyInfo {
          ProxyType proxyType = 1;
          string host = 2;
          uint32 port = 3;
          optional string username = 4;
          optional string password = 5;
        }
        """
        arg = to_message(clouddrive.pb2.GetCloudAPIConfigRequest, arg)
        if async_:
            return self.async_stub.GetCloudAPIConfig(arg, metadata=self.metadata)
        else:
            return self.stub.GetCloudAPIConfig(arg, metadata=self.metadata)

    @overload
    def SetCloudAPIConfig(
        self, 
        arg: dict | clouddrive.pb2.SetCloudAPIConfigRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def SetCloudAPIConfig(
        self, 
        arg: dict | clouddrive.pb2.SetCloudAPIConfigRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def SetCloudAPIConfig(
        self, 
        arg: dict | clouddrive.pb2.SetCloudAPIConfigRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        set CloudAPI configuration

        ------------------- protobuf rpc definition --------------------

        // set CloudAPI configuration
        rpc SetCloudAPIConfig(SetCloudAPIConfigRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message CloudAPIConfig {
          uint32 maxDownloadThreads = 1;
          uint64 minReadLengthKB = 2;
          uint64 maxReadLengthKB = 3;
          uint64 defaultReadLengthKB = 4;
          uint64 maxBufferPoolSizeMB = 5;
          double maxQueriesPerSecond = 6;
          bool forceIpv4 = 7;
          optional ProxyInfo apiProxy = 8;
          optional ProxyInfo dataProxy = 9;
          optional string customUserAgent = 10;
          optional uint32 maxUploadThreads = 11;
        }
        message SetCloudAPIConfigRequest {
          string cloudName = 1;
          string userName = 2;
          CloudAPIConfig config = 3;
        }
        """
        if async_:
            async def request():
                await self.async_stub.SetCloudAPIConfig(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.SetCloudAPIConfig(arg, metadata=self.metadata)
            return None

    @overload
    def GetSystemSettings(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.SystemSettings:
        ...
    @overload
    def GetSystemSettings(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.SystemSettings]:
        ...
    def GetSystemSettings(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.SystemSettings | Coroutine[Any, Any, clouddrive.pb2.SystemSettings]:
        """
        get all system setings value

        ------------------- protobuf rpc definition --------------------

        // get all system setings value
        rpc GetSystemSettings(google.protobuf.Empty) returns (SystemSettings) {}

        ------------------- protobuf type definition -------------------

        enum LogLevel {
          Trace = 0;
          Debug = 1;
          Info = 2;
          Warn = 3;
          Error = 4;
        }
        message StringList { repeated string values = 1; }
        message SystemSettings {
          // 0 means never expire, will live forever
          optional uint64 dirCacheTimeToLiveSecs = 1;
          optional uint64 maxPreProcessTasks = 2;
          optional uint64 maxProcessTasks = 3;
          optional string tempFileLocation = 4;
          optional bool syncWithCloud = 5;
          // time in secs to clear download task when no read operation
          optional uint64 readDownloaderTimeoutSecs = 6;
          // time in secs to wait before upload a local temp file
          optional uint64 uploadDelaySecs = 7;
          optional StringList processBlackList = 8;
          optional StringList uploadIgnoredExtensions = 9;
          optional UpdateChannel updateChannel = 10;
          optional double maxDownloadSpeedKBytesPerSecond = 11;
          optional double maxUploadSpeedKBytesPerSecond = 12;
          optional string deviceName = 13;
          optional bool dirCachePersistence = 14;
          optional string dirCacheDbLocation = 15;
          optional LogLevel fileLogLevel = 16;
          optional LogLevel terminalLogLevel = 17;
          optional LogLevel backupLogLevel = 18;
        }
        enum UpdateChannel {
          Release = 0;
          Beta = 1;
        }
        """
        if async_:
            return self.async_stub.GetSystemSettings(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetSystemSettings(Empty(), metadata=self.metadata)

    @overload
    def SetSystemSettings(
        self, 
        arg: dict | clouddrive.pb2.SystemSettings, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def SetSystemSettings(
        self, 
        arg: dict | clouddrive.pb2.SystemSettings, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def SetSystemSettings(
        self, 
        arg: dict | clouddrive.pb2.SystemSettings, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        set selected system settings value

        ------------------- protobuf rpc definition --------------------

        // set selected system settings value
        rpc SetSystemSettings(SystemSettings) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        enum LogLevel {
          Trace = 0;
          Debug = 1;
          Info = 2;
          Warn = 3;
          Error = 4;
        }
        message StringList { repeated string values = 1; }
        message SystemSettings {
          // 0 means never expire, will live forever
          optional uint64 dirCacheTimeToLiveSecs = 1;
          optional uint64 maxPreProcessTasks = 2;
          optional uint64 maxProcessTasks = 3;
          optional string tempFileLocation = 4;
          optional bool syncWithCloud = 5;
          // time in secs to clear download task when no read operation
          optional uint64 readDownloaderTimeoutSecs = 6;
          // time in secs to wait before upload a local temp file
          optional uint64 uploadDelaySecs = 7;
          optional StringList processBlackList = 8;
          optional StringList uploadIgnoredExtensions = 9;
          optional UpdateChannel updateChannel = 10;
          optional double maxDownloadSpeedKBytesPerSecond = 11;
          optional double maxUploadSpeedKBytesPerSecond = 12;
          optional string deviceName = 13;
          optional bool dirCachePersistence = 14;
          optional string dirCacheDbLocation = 15;
          optional LogLevel fileLogLevel = 16;
          optional LogLevel terminalLogLevel = 17;
          optional LogLevel backupLogLevel = 18;
        }
        enum UpdateChannel {
          Release = 0;
          Beta = 1;
        }
        """
        if async_:
            async def request():
                await self.async_stub.SetSystemSettings(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.SetSystemSettings(arg, metadata=self.metadata)
            return None

    @overload
    def SetDirCacheTimeSecs(
        self, 
        arg: dict | clouddrive.pb2.SetDirCacheTimeRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def SetDirCacheTimeSecs(
        self, 
        arg: dict | clouddrive.pb2.SetDirCacheTimeRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def SetDirCacheTimeSecs(
        self, 
        arg: dict | clouddrive.pb2.SetDirCacheTimeRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        set dir cache time

        ------------------- protobuf rpc definition --------------------

        // set dir cache time
        rpc SetDirCacheTimeSecs(SetDirCacheTimeRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message SetDirCacheTimeRequest {
          string path = 1;
          // if not present, please delete the value to restore default
          optional uint64 dirCachTimeToLiveSecs = 2;
        }
        """
        if async_:
            async def request():
                await self.async_stub.SetDirCacheTimeSecs(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.SetDirCacheTimeSecs(arg, metadata=self.metadata)
            return None

    @overload
    def GetEffectiveDirCacheTimeSecs(
        self, 
        arg: dict | clouddrive.pb2.GetEffectiveDirCacheTimeRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.GetEffectiveDirCacheTimeResult:
        ...
    @overload
    def GetEffectiveDirCacheTimeSecs(
        self, 
        arg: dict | clouddrive.pb2.GetEffectiveDirCacheTimeRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.GetEffectiveDirCacheTimeResult]:
        ...
    def GetEffectiveDirCacheTimeSecs(
        self, 
        arg: dict | clouddrive.pb2.GetEffectiveDirCacheTimeRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.GetEffectiveDirCacheTimeResult | Coroutine[Any, Any, clouddrive.pb2.GetEffectiveDirCacheTimeResult]:
        """
        get dir cache time in effect (default value will be returned)

        ------------------- protobuf rpc definition --------------------

        // get dir cache time in effect (default value will be returned)
        rpc GetEffectiveDirCacheTimeSecs(GetEffectiveDirCacheTimeRequest)
        returns (GetEffectiveDirCacheTimeResult) {}

        ------------------- protobuf type definition -------------------

        message GetEffectiveDirCacheTimeRequest { string path = 1; }
        message GetEffectiveDirCacheTimeResult { uint64 dirCacheTimeSecs = 1; }
        """
        arg = to_message(clouddrive.pb2.GetEffectiveDirCacheTimeRequest, arg)
        if async_:
            return self.async_stub.GetEffectiveDirCacheTimeSecs(arg, metadata=self.metadata)
        else:
            return self.stub.GetEffectiveDirCacheTimeSecs(arg, metadata=self.metadata)

    @overload
    def ForceExpireDirCache(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def ForceExpireDirCache(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def ForceExpireDirCache(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        force expire dir cache recursively

        ------------------- protobuf rpc definition --------------------

        // force expire dir cache recursively
        rpc ForceExpireDirCache(FileRequest) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message FileRequest { string path = 1; }
        """
        if async_:
            async def request():
                await self.async_stub.ForceExpireDirCache(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.ForceExpireDirCache(arg, metadata=self.metadata)
            return None

    @overload
    def GetOpenFileTable(
        self, 
        arg: dict | clouddrive.pb2.GetOpenFileTableRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.OpenFileTable:
        ...
    @overload
    def GetOpenFileTable(
        self, 
        arg: dict | clouddrive.pb2.GetOpenFileTableRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.OpenFileTable]:
        ...
    def GetOpenFileTable(
        self, 
        arg: dict | clouddrive.pb2.GetOpenFileTableRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.OpenFileTable | Coroutine[Any, Any, clouddrive.pb2.OpenFileTable]:
        """
        get open file table

        ------------------- protobuf rpc definition --------------------

        // get open file table
        rpc GetOpenFileTable(GetOpenFileTableRequest) returns (OpenFileTable) {}

        ------------------- protobuf type definition -------------------

        message GetOpenFileTableRequest { bool includeDir = 1; }
        message OpenFileTable {
          map<uint64, string> openFileTable = 1;
          uint64 localOpenFileCount = 2;
        }
        """
        arg = to_message(clouddrive.pb2.GetOpenFileTableRequest, arg)
        if async_:
            return self.async_stub.GetOpenFileTable(arg, metadata=self.metadata)
        else:
            return self.stub.GetOpenFileTable(arg, metadata=self.metadata)

    @overload
    def GetDirCacheTable(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.DirCacheTable:
        ...
    @overload
    def GetDirCacheTable(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.DirCacheTable]:
        ...
    def GetDirCacheTable(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.DirCacheTable | Coroutine[Any, Any, clouddrive.pb2.DirCacheTable]:
        """
        get dir cache table

        ------------------- protobuf rpc definition --------------------

        // get dir cache table
        rpc GetDirCacheTable(google.protobuf.Empty) returns (DirCacheTable) {}

        ------------------- protobuf type definition -------------------

        message DirCacheTable { map<string, DirCacheItem> dirCacheTable = 1; }
        """
        if async_:
            return self.async_stub.GetDirCacheTable(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetDirCacheTable(Empty(), metadata=self.metadata)

    @overload
    def GetReferencedEntryPaths(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.StringList:
        ...
    @overload
    def GetReferencedEntryPaths(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.StringList]:
        ...
    def GetReferencedEntryPaths(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.StringList | Coroutine[Any, Any, clouddrive.pb2.StringList]:
        """
        get referenced entry paths of parent path

        ------------------- protobuf rpc definition --------------------

        // get referenced entry paths of parent path
        rpc GetReferencedEntryPaths(FileRequest) returns (StringList) {}

        ------------------- protobuf type definition -------------------

        message FileRequest { string path = 1; }
        message StringList { repeated string values = 1; }
        """
        arg = to_message(clouddrive.pb2.FileRequest, arg)
        if async_:
            return self.async_stub.GetReferencedEntryPaths(arg, metadata=self.metadata)
        else:
            return self.stub.GetReferencedEntryPaths(arg, metadata=self.metadata)

    @overload
    def GetTempFileTable(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.TempFileTable:
        ...
    @overload
    def GetTempFileTable(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.TempFileTable]:
        ...
    def GetTempFileTable(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.TempFileTable | Coroutine[Any, Any, clouddrive.pb2.TempFileTable]:
        """
        get temp file table

        ------------------- protobuf rpc definition --------------------

        // get temp file table
        rpc GetTempFileTable(google.protobuf.Empty) returns (TempFileTable) {}

        ------------------- protobuf type definition -------------------

        message TempFileTable {
          uint64 count = 1;
          repeated string tempFiles = 2;
        }
        """
        if async_:
            return self.async_stub.GetTempFileTable(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetTempFileTable(Empty(), metadata=self.metadata)

    @overload
    def PushTaskChange(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> Iterable[clouddrive.pb2.GetAllTasksCountResult]:
        ...
    @overload
    def PushTaskChange(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Iterable[clouddrive.pb2.GetAllTasksCountResult]]:
        ...
    def PushTaskChange(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Iterable[clouddrive.pb2.GetAllTasksCountResult] | Coroutine[Any, Any, Iterable[clouddrive.pb2.GetAllTasksCountResult]]:
        """
        [deprecated] use PushMessage instead
        push upload/download task count changes to client, also can be used for
        client to detect conenction broken

        ------------------- protobuf rpc definition --------------------

        // [deprecated] use PushMessage instead
        // push upload/download task count changes to client, also can be used for
        // client to detect conenction broken
        rpc PushTaskChange(google.protobuf.Empty)
            returns (stream GetAllTasksCountResult) {}

        ------------------- protobuf type definition -------------------

        message GetAllTasksCountResult {
          uint32 downloadCount = 1;
          uint32 uploadCount = 2;
          PushMessage pushMessage = 3;
          bool hasUpdate = 4;
          repeated UploadFileInfo uploadFileStatusChanges = 5; //upload file status changed
        }
        message PushMessage { string clouddriveVersion = 1; }
        message UploadFileInfo {
          string key = 1;
          string destPath = 2;
          uint64 size = 3;
          uint64 transferedBytes = 4;
          string status = 5;
          string errorMessage = 6;
        }
        """
        if async_:
            return self.async_stub.PushTaskChange(Empty(), metadata=self.metadata)
        else:
            return self.stub.PushTaskChange(Empty(), metadata=self.metadata)

    @overload
    def PushMessage(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> Iterable[clouddrive.pb2.CloudDrivePushMessage]:
        ...
    @overload
    def PushMessage(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, Iterable[clouddrive.pb2.CloudDrivePushMessage]]:
        ...
    def PushMessage(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> Iterable[clouddrive.pb2.CloudDrivePushMessage] | Coroutine[Any, Any, Iterable[clouddrive.pb2.CloudDrivePushMessage]]:
        """
        general message notification

        ------------------- protobuf rpc definition --------------------

        // general message notification
        rpc PushMessage(google.protobuf.Empty) returns (stream CloudDrivePushMessage) {}

        ------------------- protobuf type definition -------------------

        message CloudDrivePushMessage {
          enum MessageType {
            DOWNLOADER_COUNT = 0;
            UPLOADER_COUNT = 1;
            UPDATE_STATUS = 2;
            FORCE_EXIT = 3;
            FILE_SYSTEM_CHANGE = 4;
            MOUNT_POINT_CHANGE = 5;
          }
          MessageType messageType = 1;
          oneof data {
            TransferTaskStatus transferTaskStatus = 2;
            UpdateStatus updateStatus = 3;
            ExitedMessage exitedMessage = 4;
            FileSystemChange fileSystemChange = 5;
            MountPointChange mountPointChange = 6;
          }
        }
        message ExitedMessage {
          enum ExitReason {
            UNKNOWN = 0;
            KICKEDOUT_BY_USER = 1;
            KICKEDOUT_BY_SERVER = 2;
            PASSWORD_CHANGED = 3;
            RESTART = 4;
            SHUTDOWN = 5;
          }
          ExitReason exitReason = 1;
          string message = 2; 
        }
        message FileSystemChange {
          enum ChangeType {
            CREATE = 0;
            DELETE = 1;
            RENAME = 2;
          }
          ChangeType changeType = 1;
          bool isDirectory = 2;
          string path = 3;
          //only used for RENAME type
          optional string newPath = 4;
          //not available for DELETE type
          optional CloudDriveFile theFile = 5;
        }
        message MountPointChange {
          enum ActionType {
            MOUNT = 0;
            UNMOUNT = 1;
          }
          ActionType actionType = 1;
          string mountPoint = 2;
          bool success = 3;
          string failReason = 4;
        }
        message UpdateStatus {
          enum UpdatePhase {
            NO_UPDATE = 0;
            DOWNLOADING = 1;
            READY_TO_UPDATE = 2;
            UPDATING = 3;
            UPDATE_SUCCESS = 4;
            UPDATE_FAILED = 5;
          }
          UpdatePhase updatePhase = 1;
          optional string newVersion = 2;
          optional string message = 3;
        }
        """
        if async_:
            return self.async_stub.PushMessage(Empty(), metadata=self.metadata)
        else:
            return self.stub.PushMessage(Empty(), metadata=self.metadata)

    @overload
    def GetCloudDrive1UserData(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.StringResult:
        ...
    @overload
    def GetCloudDrive1UserData(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.StringResult]:
        ...
    def GetCloudDrive1UserData(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.StringResult | Coroutine[Any, Any, clouddrive.pb2.StringResult]:
        """
        get CloudDrive1's user data string

        ------------------- protobuf rpc definition --------------------

        // get CloudDrive1's user data string
        rpc GetCloudDrive1UserData(google.protobuf.Empty) returns (StringResult) {}

        ------------------- protobuf type definition -------------------

        message StringResult { string result = 1; }
        """
        if async_:
            return self.async_stub.GetCloudDrive1UserData(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetCloudDrive1UserData(Empty(), metadata=self.metadata)

    @overload
    def RestartService(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def RestartService(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def RestartService(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        restart service

        ------------------- protobuf rpc definition --------------------

        // restart service
        rpc RestartService(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        if async_:
            async def request():
                await self.async_stub.RestartService(Empty(), metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.RestartService(Empty(), metadata=self.metadata)
            return None

    @overload
    def ShutdownService(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def ShutdownService(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def ShutdownService(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        shutdown service

        ------------------- protobuf rpc definition --------------------

        // shutdown service
        rpc ShutdownService(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        if async_:
            async def request():
                await self.async_stub.ShutdownService(Empty(), metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.ShutdownService(Empty(), metadata=self.metadata)
            return None

    @overload
    def HasUpdate(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.UpdateResult:
        ...
    @overload
    def HasUpdate(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.UpdateResult]:
        ...
    def HasUpdate(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.UpdateResult | Coroutine[Any, Any, clouddrive.pb2.UpdateResult]:
        """
        check if has updates available

        ------------------- protobuf rpc definition --------------------

        // check if has updates available
        rpc HasUpdate(google.protobuf.Empty) returns (UpdateResult) {}

        ------------------- protobuf type definition -------------------

        message UpdateResult {
          bool hasUpdate = 1;
          string newVersion = 2;
          string description = 3;
        }
        """
        if async_:
            return self.async_stub.HasUpdate(Empty(), metadata=self.metadata)
        else:
            return self.stub.HasUpdate(Empty(), metadata=self.metadata)

    @overload
    def CheckUpdate(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.UpdateResult:
        ...
    @overload
    def CheckUpdate(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.UpdateResult]:
        ...
    def CheckUpdate(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.UpdateResult | Coroutine[Any, Any, clouddrive.pb2.UpdateResult]:
        """
        check software updates

        ------------------- protobuf rpc definition --------------------

        // check software updates
        rpc CheckUpdate(google.protobuf.Empty) returns (UpdateResult) {}

        ------------------- protobuf type definition -------------------

        message UpdateResult {
          bool hasUpdate = 1;
          string newVersion = 2;
          string description = 3;
        }
        """
        if async_:
            return self.async_stub.CheckUpdate(Empty(), metadata=self.metadata)
        else:
            return self.stub.CheckUpdate(Empty(), metadata=self.metadata)

    @overload
    def DownloadUpdate(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def DownloadUpdate(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def DownloadUpdate(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        download newest version

        ------------------- protobuf rpc definition --------------------

        // download newest version
        rpc DownloadUpdate(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        if async_:
            async def request():
                await self.async_stub.DownloadUpdate(Empty(), metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.DownloadUpdate(Empty(), metadata=self.metadata)
            return None

    @overload
    def UpdateSystem(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def UpdateSystem(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def UpdateSystem(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        update to newest version

        ------------------- protobuf rpc definition --------------------

        // update to newest version
        rpc UpdateSystem(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        if async_:
            async def request():
                await self.async_stub.UpdateSystem(Empty(), metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.UpdateSystem(Empty(), metadata=self.metadata)
            return None

    @overload
    def TestUpdate(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def TestUpdate(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def TestUpdate(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        test update process

        ------------------- protobuf rpc definition --------------------

        // test update process
        rpc TestUpdate(FileRequest) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message FileRequest { string path = 1; }
        """
        if async_:
            async def request():
                await self.async_stub.TestUpdate(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.TestUpdate(arg, metadata=self.metadata)
            return None

    @overload
    def GetMetaData(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileMetaData:
        ...
    @overload
    def GetMetaData(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileMetaData]:
        ...
    def GetMetaData(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileMetaData | Coroutine[Any, Any, clouddrive.pb2.FileMetaData]:
        """
        get file metadata

        ------------------- protobuf rpc definition --------------------

        // get file metadata
        rpc GetMetaData(FileRequest) returns (FileMetaData) {}

        ------------------- protobuf type definition -------------------

        message FileMetaData { map<string, string> metadata = 1; }
        message FileRequest { string path = 1; }
        """
        arg = to_message(clouddrive.pb2.FileRequest, arg)
        if async_:
            return self.async_stub.GetMetaData(arg, metadata=self.metadata)
        else:
            return self.stub.GetMetaData(arg, metadata=self.metadata)

    @overload
    def GetOriginalPath(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.StringResult:
        ...
    @overload
    def GetOriginalPath(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.StringResult]:
        ...
    def GetOriginalPath(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.StringResult | Coroutine[Any, Any, clouddrive.pb2.StringResult]:
        """
        get file's original path from search result

        ------------------- protobuf rpc definition --------------------

        // get file's original path from search result
        rpc GetOriginalPath(FileRequest) returns (StringResult) {}

        ------------------- protobuf type definition -------------------

        message FileRequest { string path = 1; }
        message StringResult { string result = 1; }
        """
        arg = to_message(clouddrive.pb2.FileRequest, arg)
        if async_:
            return self.async_stub.GetOriginalPath(arg, metadata=self.metadata)
        else:
            return self.stub.GetOriginalPath(arg, metadata=self.metadata)

    @overload
    def ChangePassword(
        self, 
        arg: dict | clouddrive.pb2.ChangePasswordRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def ChangePassword(
        self, 
        arg: dict | clouddrive.pb2.ChangePasswordRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def ChangePassword(
        self, 
        arg: dict | clouddrive.pb2.ChangePasswordRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        change password

        ------------------- protobuf rpc definition --------------------

        // change password
        rpc ChangePassword(ChangePasswordRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message ChangePasswordRequest {
          string oldPassword = 1;
          string newPassword = 2;
        }
        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        """
        arg = to_message(clouddrive.pb2.ChangePasswordRequest, arg)
        if async_:
            return self.async_stub.ChangePassword(arg, metadata=self.metadata)
        else:
            return self.stub.ChangePassword(arg, metadata=self.metadata)

    @overload
    def CreateFile(
        self, 
        arg: dict | clouddrive.pb2.CreateFileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.CreateFileResult:
        ...
    @overload
    def CreateFile(
        self, 
        arg: dict | clouddrive.pb2.CreateFileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.CreateFileResult]:
        ...
    def CreateFile(
        self, 
        arg: dict | clouddrive.pb2.CreateFileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.CreateFileResult | Coroutine[Any, Any, clouddrive.pb2.CreateFileResult]:
        """
        create a new file

        ------------------- protobuf rpc definition --------------------

        // create a new file
        rpc CreateFile(CreateFileRequest) returns (CreateFileResult) {}

        ------------------- protobuf type definition -------------------

        message CreateFileRequest {
          string parentPath = 1;
          string fileName = 2;
        }
        message CreateFileResult { uint64 fileHandle = 1; }
        """
        arg = to_message(clouddrive.pb2.CreateFileRequest, arg)
        if async_:
            return self.async_stub.CreateFile(arg, metadata=self.metadata)
        else:
            return self.stub.CreateFile(arg, metadata=self.metadata)

    @overload
    def CloseFile(
        self, 
        arg: dict | clouddrive.pb2.CloseFileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def CloseFile(
        self, 
        arg: dict | clouddrive.pb2.CloseFileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def CloseFile(
        self, 
        arg: dict | clouddrive.pb2.CloseFileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        close an opened file

        ------------------- protobuf rpc definition --------------------

        // close an opened file
        rpc CloseFile(CloseFileRequest) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message CloseFileRequest { uint64 fileHandle = 1; }
        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        """
        arg = to_message(clouddrive.pb2.CloseFileRequest, arg)
        if async_:
            return self.async_stub.CloseFile(arg, metadata=self.metadata)
        else:
            return self.stub.CloseFile(arg, metadata=self.metadata)

    @overload
    def WriteToFileStream(
        self, 
        arg: Sequence[dict | clouddrive.pb2.WriteFileRequest], 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.WriteFileResult:
        ...
    @overload
    def WriteToFileStream(
        self, 
        arg: Sequence[dict | clouddrive.pb2.WriteFileRequest], 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.WriteFileResult]:
        ...
    def WriteToFileStream(
        self, 
        arg: Sequence[dict | clouddrive.pb2.WriteFileRequest], 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.WriteFileResult | Coroutine[Any, Any, clouddrive.pb2.WriteFileResult]:
        """
        write a stream to an opened file

        ------------------- protobuf rpc definition --------------------

        // write a stream to an opened file
        rpc WriteToFileStream(stream WriteFileRequest) returns (WriteFileResult) {}

        ------------------- protobuf type definition -------------------

        message WriteFileRequest {
          uint64 fileHandle = 1;
          uint64 startPos = 2;
          uint64 length = 3;
          bytes buffer = 4;
          bool closeFile = 5;
        }
        message WriteFileResult { uint64 bytesWritten = 1; }
        """
        arg = [to_message(clouddrive.pb2.WriteFileRequest, a) for a in arg]
        if async_:
            return self.async_stub.WriteToFileStream(arg, metadata=self.metadata)
        else:
            return self.stub.WriteToFileStream(arg, metadata=self.metadata)

    @overload
    def WriteToFile(
        self, 
        arg: dict | clouddrive.pb2.WriteFileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.WriteFileResult:
        ...
    @overload
    def WriteToFile(
        self, 
        arg: dict | clouddrive.pb2.WriteFileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.WriteFileResult]:
        ...
    def WriteToFile(
        self, 
        arg: dict | clouddrive.pb2.WriteFileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.WriteFileResult | Coroutine[Any, Any, clouddrive.pb2.WriteFileResult]:
        """
        write to an opened file

        ------------------- protobuf rpc definition --------------------

        // write to an opened file
        rpc WriteToFile(WriteFileRequest) returns (WriteFileResult) {}

        ------------------- protobuf type definition -------------------

        message WriteFileRequest {
          uint64 fileHandle = 1;
          uint64 startPos = 2;
          uint64 length = 3;
          bytes buffer = 4;
          bool closeFile = 5;
        }
        message WriteFileResult { uint64 bytesWritten = 1; }
        """
        arg = to_message(clouddrive.pb2.WriteFileRequest, arg)
        if async_:
            return self.async_stub.WriteToFile(arg, metadata=self.metadata)
        else:
            return self.stub.WriteToFile(arg, metadata=self.metadata)

    @overload
    def GetPromotions(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.GetPromotionsResult:
        ...
    @overload
    def GetPromotions(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.GetPromotionsResult]:
        ...
    def GetPromotions(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.GetPromotionsResult | Coroutine[Any, Any, clouddrive.pb2.GetPromotionsResult]:
        """
        get promotions

        ------------------- protobuf rpc definition --------------------

        // get promotions
        rpc GetPromotions(google.protobuf.Empty) returns (GetPromotionsResult) {}

        ------------------- protobuf type definition -------------------

        message GetPromotionsResult { repeated Promotion promotions = 1; }
        message Promotion {
          string id = 1;
          string cloudName = 2;
          string title = 3;
          optional string subTitle = 4;
          string rules = 5;
          optional string notice = 6;
          string url = 7;
        }
        """
        if async_:
            return self.async_stub.GetPromotions(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetPromotions(Empty(), metadata=self.metadata)

    @overload
    def UpdatePromotionResult(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def UpdatePromotionResult(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def UpdatePromotionResult(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        update promotion result after purchased

        ------------------- protobuf rpc definition --------------------

        // update promotion result after purchased
        rpc UpdatePromotionResult(google.protobuf.Empty)
            returns (google.protobuf.Empty) {}
        """
        if async_:
            async def request():
                await self.async_stub.UpdatePromotionResult(Empty(), metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.UpdatePromotionResult(Empty(), metadata=self.metadata)
            return None

    @overload
    def GetCloudDrivePlans(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.GetCloudDrivePlansResult:
        ...
    @overload
    def GetCloudDrivePlans(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.GetCloudDrivePlansResult]:
        ...
    def GetCloudDrivePlans(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.GetCloudDrivePlansResult | Coroutine[Any, Any, clouddrive.pb2.GetCloudDrivePlansResult]:
        """
        get cloudfs plans

        ------------------- protobuf rpc definition --------------------

        // get cloudfs plans
        rpc GetCloudDrivePlans(google.protobuf.Empty)
            returns (GetCloudDrivePlansResult) {}

        ------------------- protobuf type definition -------------------

        message CloudDrivePlan {
          string id = 1;
          string name = 2;
          string description = 3;
          double price = 4;
          optional int64 duration = 5;
          string durationDescription = 6;
          bool isActive = 7;
          optional string fontAwesomeIcon = 8;
          optional double originalPrice = 9;
          repeated AccountRole planRoles = 10;
        }
        message GetCloudDrivePlansResult { repeated CloudDrivePlan plans = 1; }
        """
        if async_:
            return self.async_stub.GetCloudDrivePlans(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetCloudDrivePlans(Empty(), metadata=self.metadata)

    @overload
    def JoinPlan(
        self, 
        arg: dict | clouddrive.pb2.JoinPlanRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.JoinPlanResult:
        ...
    @overload
    def JoinPlan(
        self, 
        arg: dict | clouddrive.pb2.JoinPlanRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.JoinPlanResult]:
        ...
    def JoinPlan(
        self, 
        arg: dict | clouddrive.pb2.JoinPlanRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.JoinPlanResult | Coroutine[Any, Any, clouddrive.pb2.JoinPlanResult]:
        """
        join a plan

        ------------------- protobuf rpc definition --------------------

        // join a plan
        rpc JoinPlan(JoinPlanRequest) returns (JoinPlanResult) {}

        ------------------- protobuf type definition -------------------

        message JoinPlanRequest {
          string planId = 1;
          optional string couponCode = 2;
        }
        message JoinPlanResult {
          bool success = 1;
          double balance = 2;
          string planName = 3;
          string planDescription = 4;
          optional google.protobuf.Timestamp expireTime = 5;
          optional PaymentInfo paymentInfo = 6;
        }
        message PaymentInfo {
          string user_id = 1;
          string plan_id = 2;
          map<string, string> paymentMethods = 3;
          optional string coupon_code = 4;
          optional string machine_id = 5;
          optional string check_code = 6;
        }
        """
        arg = to_message(clouddrive.pb2.JoinPlanRequest, arg)
        if async_:
            return self.async_stub.JoinPlan(arg, metadata=self.metadata)
        else:
            return self.stub.JoinPlan(arg, metadata=self.metadata)

    @overload
    def BindCloudAccount(
        self, 
        arg: dict | clouddrive.pb2.BindCloudAccountRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def BindCloudAccount(
        self, 
        arg: dict | clouddrive.pb2.BindCloudAccountRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def BindCloudAccount(
        self, 
        arg: dict | clouddrive.pb2.BindCloudAccountRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        bind account to a cloud account id

        ------------------- protobuf rpc definition --------------------

        // bind account to a cloud account id
        rpc BindCloudAccount(BindCloudAccountRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message BindCloudAccountRequest {
          string cloudName = 1;
          string cloudAccountId = 2;
        }
        """
        if async_:
            async def request():
                await self.async_stub.BindCloudAccount(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.BindCloudAccount(arg, metadata=self.metadata)
            return None

    @overload
    def TransferBalance(
        self, 
        arg: dict | clouddrive.pb2.TransferBalanceRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def TransferBalance(
        self, 
        arg: dict | clouddrive.pb2.TransferBalanceRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def TransferBalance(
        self, 
        arg: dict | clouddrive.pb2.TransferBalanceRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        transfer balance to another user

        ------------------- protobuf rpc definition --------------------

        // transfer balance to another user
        rpc TransferBalance(TransferBalanceRequest) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message TransferBalanceRequest {
          string toUserName = 1;
          double amount = 2;
          string password = 3;
        }
        """
        if async_:
            async def request():
                await self.async_stub.TransferBalance(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.TransferBalance(arg, metadata=self.metadata)
            return None

    @overload
    def ChangeEmail(
        self, 
        arg: dict | clouddrive.pb2.ChangeUserNameEmailRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def ChangeEmail(
        self, 
        arg: dict | clouddrive.pb2.ChangeUserNameEmailRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def ChangeEmail(
        self, 
        arg: dict | clouddrive.pb2.ChangeUserNameEmailRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        change email

        ------------------- protobuf rpc definition --------------------

        // change email
        rpc ChangeEmail(ChangeUserNameEmailRequest) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message ChangeUserNameEmailRequest {
          string newUserName = 1;
          string newEmail = 2;
          string password = 3;
        }
        """
        if async_:
            async def request():
                await self.async_stub.ChangeEmail(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.ChangeEmail(arg, metadata=self.metadata)
            return None

    @overload
    def GetBalanceLog(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.BalanceLogResult:
        ...
    @overload
    def GetBalanceLog(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.BalanceLogResult]:
        ...
    def GetBalanceLog(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.BalanceLogResult | Coroutine[Any, Any, clouddrive.pb2.BalanceLogResult]:
        """
        chech balance log

        ------------------- protobuf rpc definition --------------------

        // chech balance log
        rpc GetBalanceLog(google.protobuf.Empty) returns (BalanceLogResult) {}

        ------------------- protobuf type definition -------------------

        message BalanceLog {
          double balance_before = 1;
          double balance_after = 2;
          double balance_change = 3;
          enum BalancceChangeOperation {
            Unknown = 0;
            Deposit = 1;
            Refund = 2;
          }
          BalancceChangeOperation operation = 4;
          string operation_source = 5;
          string operation_id = 6;
          google.protobuf.Timestamp operation_time = 7;
        }
        message BalanceLogResult { repeated BalanceLog logs = 1; }
        """
        if async_:
            return self.async_stub.GetBalanceLog(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetBalanceLog(Empty(), metadata=self.metadata)

    @overload
    def CheckActivationCode(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.CheckActivationCodeResult:
        ...
    @overload
    def CheckActivationCode(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.CheckActivationCodeResult]:
        ...
    def CheckActivationCode(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.CheckActivationCodeResult | Coroutine[Any, Any, clouddrive.pb2.CheckActivationCodeResult]:
        """
        check activation code for a plan

        ------------------- protobuf rpc definition --------------------

        // check activation code for a plan
        rpc CheckActivationCode(StringValue) returns (CheckActivationCodeResult) {}

        ------------------- protobuf type definition -------------------

        message CheckActivationCodeResult {
          string planId = 1;
          string planName = 2;
          string planDescription = 3;
        }
        message StringValue { string value = 1; }
        """
        arg = to_message(clouddrive.pb2.StringValue, arg)
        if async_:
            return self.async_stub.CheckActivationCode(arg, metadata=self.metadata)
        else:
            return self.stub.CheckActivationCode(arg, metadata=self.metadata)

    @overload
    def ActivatePlan(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.JoinPlanResult:
        ...
    @overload
    def ActivatePlan(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.JoinPlanResult]:
        ...
    def ActivatePlan(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.JoinPlanResult | Coroutine[Any, Any, clouddrive.pb2.JoinPlanResult]:
        """
        Activate plan using an activation code

        ------------------- protobuf rpc definition --------------------

        // Activate plan using an activation code
        rpc ActivatePlan(StringValue) returns (JoinPlanResult) {}

        ------------------- protobuf type definition -------------------

        message JoinPlanResult {
          bool success = 1;
          double balance = 2;
          string planName = 3;
          string planDescription = 4;
          optional google.protobuf.Timestamp expireTime = 5;
          optional PaymentInfo paymentInfo = 6;
        }
        message PaymentInfo {
          string user_id = 1;
          string plan_id = 2;
          map<string, string> paymentMethods = 3;
          optional string coupon_code = 4;
          optional string machine_id = 5;
          optional string check_code = 6;
        }
        message StringValue { string value = 1; }
        """
        arg = to_message(clouddrive.pb2.StringValue, arg)
        if async_:
            return self.async_stub.ActivatePlan(arg, metadata=self.metadata)
        else:
            return self.stub.ActivatePlan(arg, metadata=self.metadata)

    @overload
    def CheckCouponCode(
        self, 
        arg: dict | clouddrive.pb2.CheckCouponCodeRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.CouponCodeResult:
        ...
    @overload
    def CheckCouponCode(
        self, 
        arg: dict | clouddrive.pb2.CheckCouponCodeRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.CouponCodeResult]:
        ...
    def CheckCouponCode(
        self, 
        arg: dict | clouddrive.pb2.CheckCouponCodeRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.CouponCodeResult | Coroutine[Any, Any, clouddrive.pb2.CouponCodeResult]:
        """
        check counpon code for a plan

        ------------------- protobuf rpc definition --------------------

        // check counpon code for a plan
        rpc CheckCouponCode(CheckCouponCodeRequest) returns (CouponCodeResult) {}

        ------------------- protobuf type definition -------------------

        message CheckCouponCodeRequest {
          string planId = 1;
          string couponCode = 2;
        }
        message CouponCodeResult {
          string couponCode = 1;
          string couponDescription = 2;
          bool isPercentage = 3;
          double couponDiscountAmount = 4;
        }
        """
        arg = to_message(clouddrive.pb2.CheckCouponCodeRequest, arg)
        if async_:
            return self.async_stub.CheckCouponCode(arg, metadata=self.metadata)
        else:
            return self.stub.CheckCouponCode(arg, metadata=self.metadata)

    @overload
    def GetReferralCode(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.StringValue:
        ...
    @overload
    def GetReferralCode(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.StringValue]:
        ...
    def GetReferralCode(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.StringValue | Coroutine[Any, Any, clouddrive.pb2.StringValue]:
        """
        get referral code of current user

        ------------------- protobuf rpc definition --------------------

        // get referral code of current user
        rpc GetReferralCode(google.protobuf.Empty) returns (StringValue) {}

        ------------------- protobuf type definition -------------------

        message StringValue { string value = 1; }
        """
        if async_:
            return self.async_stub.GetReferralCode(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetReferralCode(Empty(), metadata=self.metadata)

    @overload
    def BackupGetAll(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.BackupList:
        ...
    @overload
    def BackupGetAll(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.BackupList]:
        ...
    def BackupGetAll(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.BackupList | Coroutine[Any, Any, clouddrive.pb2.BackupList]:
        """
        // list all backups

        ------------------- protobuf rpc definition --------------------

        // // list all backups
        rpc BackupGetAll(google.protobuf.Empty) returns (BackupList) {}

        ------------------- protobuf type definition -------------------

        message BackupList { repeated BackupStatus backups = 1; }
        message BackupStatus {
          enum Status {
            Idle = 0;
            WalkingThrough = 1;
            Error = 2;
            Disabled = 3;
          }
          enum FileWatchStatus {
            WatcherIdle = 0;
            Watching = 1;
            WatcherError = 2;
            WatcherDisabled = 3;
          }
          Backup backup = 1;
          Status status = 2;
          string statusMessage = 3;
          FileWatchStatus watcherStatus = 4;
          string watcherStatusMessage = 5;
        }
        """
        if async_:
            return self.async_stub.BackupGetAll(Empty(), metadata=self.metadata)
        else:
            return self.stub.BackupGetAll(Empty(), metadata=self.metadata)

    @overload
    def BackupAdd(
        self, 
        arg: dict | clouddrive.pb2.Backup, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def BackupAdd(
        self, 
        arg: dict | clouddrive.pb2.Backup, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def BackupAdd(
        self, 
        arg: dict | clouddrive.pb2.Backup, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        add a backup

        ------------------- protobuf rpc definition --------------------

        // add a backup
        rpc BackupAdd(Backup) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message Backup {
          string sourcePath = 1;
          repeated BackupDestination destinations = 2;
          repeated FileBackupRule fileBackupRules = 3;
          FileReplaceRule fileReplaceRule = 4;
          FileDeleteRule fileDeleteRule = 5;
          bool isEnabled = 6;
          bool fileSystemWatchEnabled = 7;
          int64 walkingThroughIntervalSecs = 8; // 0 means never auto walking through
          bool forceWalkingThroughOnStart = 9;
          repeated TimeSchedule timeSchedules = 10;
          bool isTimeSchedulesEnabled = 11;
        }
        message BackupDestination {
          string destinationPath = 1;
          bool isEnabled = 2;
          optional google.protobuf.Timestamp lastFinishTime = 3;
        }
        message FileBackupRule {
          oneof rule {
            string extensions = 1;
            string fileNames = 2;
            string regex = 3;
            uint64 minSize = 4;
          }
          bool isEnabled = 100;
          bool isBlackList = 101;
          bool applyToFolder = 102;
        }
        enum FileDeleteRule {
          Delete = 0;
          Recycle = 1;
          Keep = 2;
          MoveToVersionHistory = 3;
        }
        enum FileReplaceRule {
          Skip = 0;
          Overwrite = 1;
          KeepHistoryVersion = 2;
        }
        message TimeSchedule {
          bool isEnabled = 1;
          uint32 hour = 2;
          uint32 minute = 3;
          uint32 second = 4;
          optional DaysOfWeek daysOfWeek = 5; // none means every day
        }
        """
        if async_:
            async def request():
                await self.async_stub.BackupAdd(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.BackupAdd(arg, metadata=self.metadata)
            return None

    @overload
    def BackupRemove(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def BackupRemove(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def BackupRemove(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        remove a backup by it's source path

        ------------------- protobuf rpc definition --------------------

        // remove a backup by it's source path
        rpc BackupRemove(StringValue) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message StringValue { string value = 1; }
        """
        if async_:
            async def request():
                await self.async_stub.BackupRemove(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.BackupRemove(arg, metadata=self.metadata)
            return None

    @overload
    def BackupUpdate(
        self, 
        arg: dict | clouddrive.pb2.Backup, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def BackupUpdate(
        self, 
        arg: dict | clouddrive.pb2.Backup, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def BackupUpdate(
        self, 
        arg: dict | clouddrive.pb2.Backup, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        update a backup

        ------------------- protobuf rpc definition --------------------

        // update a backup
        rpc BackupUpdate(Backup) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message Backup {
          string sourcePath = 1;
          repeated BackupDestination destinations = 2;
          repeated FileBackupRule fileBackupRules = 3;
          FileReplaceRule fileReplaceRule = 4;
          FileDeleteRule fileDeleteRule = 5;
          bool isEnabled = 6;
          bool fileSystemWatchEnabled = 7;
          int64 walkingThroughIntervalSecs = 8; // 0 means never auto walking through
          bool forceWalkingThroughOnStart = 9;
          repeated TimeSchedule timeSchedules = 10;
          bool isTimeSchedulesEnabled = 11;
        }
        message BackupDestination {
          string destinationPath = 1;
          bool isEnabled = 2;
          optional google.protobuf.Timestamp lastFinishTime = 3;
        }
        message FileBackupRule {
          oneof rule {
            string extensions = 1;
            string fileNames = 2;
            string regex = 3;
            uint64 minSize = 4;
          }
          bool isEnabled = 100;
          bool isBlackList = 101;
          bool applyToFolder = 102;
        }
        enum FileDeleteRule {
          Delete = 0;
          Recycle = 1;
          Keep = 2;
          MoveToVersionHistory = 3;
        }
        enum FileReplaceRule {
          Skip = 0;
          Overwrite = 1;
          KeepHistoryVersion = 2;
        }
        message TimeSchedule {
          bool isEnabled = 1;
          uint32 hour = 2;
          uint32 minute = 3;
          uint32 second = 4;
          optional DaysOfWeek daysOfWeek = 5; // none means every day
        }
        """
        if async_:
            async def request():
                await self.async_stub.BackupUpdate(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.BackupUpdate(arg, metadata=self.metadata)
            return None

    @overload
    def BackupAddDestination(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def BackupAddDestination(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def BackupAddDestination(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        add destinations to a backup

        ------------------- protobuf rpc definition --------------------

        // add destinations to a backup
        rpc BackupAddDestination(BackupModifyRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message BackupDestination {
          string destinationPath = 1;
          bool isEnabled = 2;
          optional google.protobuf.Timestamp lastFinishTime = 3;
        }
        message BackupModifyRequest {
          string sourcePath = 1;
          repeated BackupDestination destinations = 2;
          repeated FileBackupRule fileBackupRules = 3;
          optional FileReplaceRule fileReplaceRule = 4;
          optional FileDeleteRule fileDeleteRule = 5;
          optional bool fileSystemWatchEnabled = 6;
          optional int64 walkingThroughIntervalSecs = 7;
        }
        message FileBackupRule {
          oneof rule {
            string extensions = 1;
            string fileNames = 2;
            string regex = 3;
            uint64 minSize = 4;
          }
          bool isEnabled = 100;
          bool isBlackList = 101;
          bool applyToFolder = 102;
        }
        enum FileDeleteRule {
          Delete = 0;
          Recycle = 1;
          Keep = 2;
          MoveToVersionHistory = 3;
        }
        enum FileReplaceRule {
          Skip = 0;
          Overwrite = 1;
          KeepHistoryVersion = 2;
        }
        """
        if async_:
            async def request():
                await self.async_stub.BackupAddDestination(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.BackupAddDestination(arg, metadata=self.metadata)
            return None

    @overload
    def BackupRemoveDestination(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def BackupRemoveDestination(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def BackupRemoveDestination(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        remove destinations from a backup

        ------------------- protobuf rpc definition --------------------

        // remove destinations from a backup
        rpc BackupRemoveDestination(BackupModifyRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message BackupDestination {
          string destinationPath = 1;
          bool isEnabled = 2;
          optional google.protobuf.Timestamp lastFinishTime = 3;
        }
        message BackupModifyRequest {
          string sourcePath = 1;
          repeated BackupDestination destinations = 2;
          repeated FileBackupRule fileBackupRules = 3;
          optional FileReplaceRule fileReplaceRule = 4;
          optional FileDeleteRule fileDeleteRule = 5;
          optional bool fileSystemWatchEnabled = 6;
          optional int64 walkingThroughIntervalSecs = 7;
        }
        message FileBackupRule {
          oneof rule {
            string extensions = 1;
            string fileNames = 2;
            string regex = 3;
            uint64 minSize = 4;
          }
          bool isEnabled = 100;
          bool isBlackList = 101;
          bool applyToFolder = 102;
        }
        enum FileDeleteRule {
          Delete = 0;
          Recycle = 1;
          Keep = 2;
          MoveToVersionHistory = 3;
        }
        enum FileReplaceRule {
          Skip = 0;
          Overwrite = 1;
          KeepHistoryVersion = 2;
        }
        """
        if async_:
            async def request():
                await self.async_stub.BackupRemoveDestination(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.BackupRemoveDestination(arg, metadata=self.metadata)
            return None

    @overload
    def BackupSetEnabled(
        self, 
        arg: dict | clouddrive.pb2.BackupSetEnabledRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def BackupSetEnabled(
        self, 
        arg: dict | clouddrive.pb2.BackupSetEnabledRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def BackupSetEnabled(
        self, 
        arg: dict | clouddrive.pb2.BackupSetEnabledRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        enable/disable a backup

        ------------------- protobuf rpc definition --------------------

        // enable/disable a backup
        rpc BackupSetEnabled(BackupSetEnabledRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message BackupSetEnabledRequest {
          string sourcePath = 1;
          bool isEnabled = 2;
        }
        """
        if async_:
            async def request():
                await self.async_stub.BackupSetEnabled(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.BackupSetEnabled(arg, metadata=self.metadata)
            return None

    @overload
    def BackupSetFileSystemWatchEnabled(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def BackupSetFileSystemWatchEnabled(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def BackupSetFileSystemWatchEnabled(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        enable/disable a backup's FileSystemWatch

        ------------------- protobuf rpc definition --------------------

        // enable/disable a backup's FileSystemWatch
        rpc BackupSetFileSystemWatchEnabled(BackupModifyRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message BackupDestination {
          string destinationPath = 1;
          bool isEnabled = 2;
          optional google.protobuf.Timestamp lastFinishTime = 3;
        }
        message BackupModifyRequest {
          string sourcePath = 1;
          repeated BackupDestination destinations = 2;
          repeated FileBackupRule fileBackupRules = 3;
          optional FileReplaceRule fileReplaceRule = 4;
          optional FileDeleteRule fileDeleteRule = 5;
          optional bool fileSystemWatchEnabled = 6;
          optional int64 walkingThroughIntervalSecs = 7;
        }
        message FileBackupRule {
          oneof rule {
            string extensions = 1;
            string fileNames = 2;
            string regex = 3;
            uint64 minSize = 4;
          }
          bool isEnabled = 100;
          bool isBlackList = 101;
          bool applyToFolder = 102;
        }
        enum FileDeleteRule {
          Delete = 0;
          Recycle = 1;
          Keep = 2;
          MoveToVersionHistory = 3;
        }
        enum FileReplaceRule {
          Skip = 0;
          Overwrite = 1;
          KeepHistoryVersion = 2;
        }
        """
        if async_:
            async def request():
                await self.async_stub.BackupSetFileSystemWatchEnabled(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.BackupSetFileSystemWatchEnabled(arg, metadata=self.metadata)
            return None

    @overload
    def BackupUpdateStrategies(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def BackupUpdateStrategies(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def BackupUpdateStrategies(
        self, 
        arg: dict | clouddrive.pb2.BackupModifyRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        deprecated, use BackupUpdate instead

        ------------------- protobuf rpc definition --------------------

        // deprecated, use BackupUpdate instead
        rpc BackupUpdateStrategies(BackupModifyRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message BackupDestination {
          string destinationPath = 1;
          bool isEnabled = 2;
          optional google.protobuf.Timestamp lastFinishTime = 3;
        }
        message BackupModifyRequest {
          string sourcePath = 1;
          repeated BackupDestination destinations = 2;
          repeated FileBackupRule fileBackupRules = 3;
          optional FileReplaceRule fileReplaceRule = 4;
          optional FileDeleteRule fileDeleteRule = 5;
          optional bool fileSystemWatchEnabled = 6;
          optional int64 walkingThroughIntervalSecs = 7;
        }
        message FileBackupRule {
          oneof rule {
            string extensions = 1;
            string fileNames = 2;
            string regex = 3;
            uint64 minSize = 4;
          }
          bool isEnabled = 100;
          bool isBlackList = 101;
          bool applyToFolder = 102;
        }
        enum FileDeleteRule {
          Delete = 0;
          Recycle = 1;
          Keep = 2;
          MoveToVersionHistory = 3;
        }
        enum FileReplaceRule {
          Skip = 0;
          Overwrite = 1;
          KeepHistoryVersion = 2;
        }
        """
        if async_:
            async def request():
                await self.async_stub.BackupUpdateStrategies(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.BackupUpdateStrategies(arg, metadata=self.metadata)
            return None

    @overload
    def BackupRestartWalkingThrough(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def BackupRestartWalkingThrough(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def BackupRestartWalkingThrough(
        self, 
        arg: dict | clouddrive.pb2.StringValue, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        restart a backup walking through

        ------------------- protobuf rpc definition --------------------

        // restart a backup walking through
        rpc BackupRestartWalkingThrough(StringValue) returns (google.protobuf.Empty) {
        }

        ------------------- protobuf type definition -------------------

        message StringValue { string value = 1; }
        """
        if async_:
            async def request():
                await self.async_stub.BackupRestartWalkingThrough(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.BackupRestartWalkingThrough(arg, metadata=self.metadata)
            return None

    @overload
    def CanAddMoreBackups(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileOperationResult:
        ...
    @overload
    def CanAddMoreBackups(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        ...
    def CanAddMoreBackups(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileOperationResult | Coroutine[Any, Any, clouddrive.pb2.FileOperationResult]:
        """
        check if current plan can support more backups

        ------------------- protobuf rpc definition --------------------

        // check if current plan can support more backups
        rpc CanAddMoreBackups(google.protobuf.Empty) returns (FileOperationResult) {}

        ------------------- protobuf type definition -------------------

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
          repeated string resultFilePaths = 3;
        }
        """
        if async_:
            return self.async_stub.CanAddMoreBackups(Empty(), metadata=self.metadata)
        else:
            return self.stub.CanAddMoreBackups(Empty(), metadata=self.metadata)

    @overload
    def GetMachineId(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.StringResult:
        ...
    @overload
    def GetMachineId(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.StringResult]:
        ...
    def GetMachineId(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.StringResult | Coroutine[Any, Any, clouddrive.pb2.StringResult]:
        """
        get machine id

        ------------------- protobuf rpc definition --------------------

        // get machine id
        rpc GetMachineId(google.protobuf.Empty) returns (StringResult) {}

        ------------------- protobuf type definition -------------------

        message StringResult { string result = 1; }
        """
        if async_:
            return self.async_stub.GetMachineId(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetMachineId(Empty(), metadata=self.metadata)

    @overload
    def GetOnlineDevices(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.OnlineDevices:
        ...
    @overload
    def GetOnlineDevices(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.OnlineDevices]:
        ...
    def GetOnlineDevices(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.OnlineDevices | Coroutine[Any, Any, clouddrive.pb2.OnlineDevices]:
        """
        get online devices

        ------------------- protobuf rpc definition --------------------

        // get online devices
        rpc GetOnlineDevices(google.protobuf.Empty) returns (OnlineDevices) {}

        ------------------- protobuf type definition -------------------

        message Device {
          string deviceId = 1;
          string deviceName = 2;
          string osType = 3;
          string version = 4;
          string ipAddress = 5;
          google.protobuf.Timestamp lastUpdateTime = 6;
        }
        message OnlineDevices {
          repeated Device devices = 1;
        }
        """
        if async_:
            return self.async_stub.GetOnlineDevices(Empty(), metadata=self.metadata)
        else:
            return self.stub.GetOnlineDevices(Empty(), metadata=self.metadata)

    @overload
    def KickoutDevice(
        self, 
        arg: dict | clouddrive.pb2.DeviceRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> None:
        ...
    @overload
    def KickoutDevice(
        self, 
        arg: dict | clouddrive.pb2.DeviceRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, None]:
        ...
    def KickoutDevice(
        self, 
        arg: dict | clouddrive.pb2.DeviceRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> None | Coroutine[Any, Any, None]:
        """
        kickout a device

        ------------------- protobuf rpc definition --------------------

        // kickout a device
        rpc KickoutDevice(DeviceRequest) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message DeviceRequest {
          string deviceId = 1;
        }
        """
        if async_:
            async def request():
                await self.async_stub.KickoutDevice(arg, metadata=self.metadata)
                return None
            return request()
        else:
            self.stub.KickoutDevice(arg, metadata=self.metadata)
            return None

    @overload
    def ListLogFiles(
        self, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.ListLogFileResult:
        ...
    @overload
    def ListLogFiles(
        self, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.ListLogFileResult]:
        ...
    def ListLogFiles(
        self, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.ListLogFileResult | Coroutine[Any, Any, clouddrive.pb2.ListLogFileResult]:
        """
        list log file names

        ------------------- protobuf rpc definition --------------------

        // list log file names
        rpc ListLogFiles(google.protobuf.Empty) returns (ListLogFileResult) {}

        ------------------- protobuf type definition -------------------

        message ListLogFileResult {
          repeated LogFileRecord logFiles = 1;
        }
        message LogFileRecord {
          string fileName = 1;
          google.protobuf.Timestamp lastModifiedTime = 2;
          uint64 fileSize = 3;
        }
        """
        if async_:
            return self.async_stub.ListLogFiles(Empty(), metadata=self.metadata)
        else:
            return self.stub.ListLogFiles(Empty(), metadata=self.metadata)

    @overload
    def SyncFileChangesFromCloud(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False] = False, 
    ) -> clouddrive.pb2.FileSystemChangeStatistics:
        ...
    @overload
    def SyncFileChangesFromCloud(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[True], 
    ) -> Coroutine[Any, Any, clouddrive.pb2.FileSystemChangeStatistics]:
        ...
    def SyncFileChangesFromCloud(
        self, 
        arg: dict | clouddrive.pb2.FileRequest, 
        /, 
        async_: Literal[False, True] = False, 
    ) -> clouddrive.pb2.FileSystemChangeStatistics | Coroutine[Any, Any, clouddrive.pb2.FileSystemChangeStatistics]:
        """
        sync file changes from cloud

        ------------------- protobuf rpc definition --------------------

        // sync file changes from cloud
        rpc SyncFileChangesFromCloud(FileRequest) returns (FileSystemChangeStatistics) {}

        ------------------- protobuf type definition -------------------

        message FileRequest { string path = 1; }
        message FileSystemChangeStatistics {
          uint64 createCount = 1;
          uint64 deleteCount = 2;
          uint64 renameCount = 3;
        }
        """
        arg = to_message(clouddrive.pb2.FileRequest, arg)
        if async_:
            return self.async_stub.SyncFileChangesFromCloud(arg, metadata=self.metadata)
        else:
            return self.stub.SyncFileChangesFromCloud(arg, metadata=self.metadata)

