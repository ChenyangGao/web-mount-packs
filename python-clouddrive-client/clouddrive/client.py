#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io>"
__all__ = ["Client", "CLOUDDRIVE_API_MAP"]

from functools import cached_property
from typing import Any, Iterator, Never, Optional
from urllib.parse import urlsplit, urlunsplit

from google.protobuf.empty_pb2 import Empty # type: ignore
from grpc import insecure_channel, Channel # type: ignore
from grpclib.client import Channel as AsyncChannel # type: ignore
from yarl import URL

import pathlib, sys
PROTO_DIR = str(pathlib.Path(__file__).parent / "proto")
if PROTO_DIR not in sys.path:
    sys.path.append(PROTO_DIR)

import CloudDrive_pb2 # type: ignore
import CloudDrive_pb2_grpc # type: ignore
import CloudDrive_grpc # type: ignore


CLOUDDRIVE_API_MAP = {
    "GetSystemInfo": {"return": CloudDrive_pb2.CloudDriveSystemInfo}, 
    "GetToken": {"argument": CloudDrive_pb2.GetTokenRequest, "return": CloudDrive_pb2.JWTToken}, 
    "Login": {"argument": CloudDrive_pb2.UserLoginRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "Register": {"argument": CloudDrive_pb2.UserRegisterRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "SendResetAccountEmail": {"argument": CloudDrive_pb2.SendResetAccountEmailRequest}, 
    "ResetAccount": {"argument": CloudDrive_pb2.ResetAccountRequest}, 
    "SendConfirmEmail": {}, 
    "ConfirmEmail": {"argument": CloudDrive_pb2.ConfirmEmailRequest}, 
    "GetAccountStatus": {"return": CloudDrive_pb2.AccountStatusResult}, 
    "GetSubFiles": {"argument": CloudDrive_pb2.ListSubFileRequest, "return": Iterator[CloudDrive_pb2.SubFilesReply]}, 
    "GetSearchResults": {"argument": CloudDrive_pb2.SearchRequest, "return": Iterator[CloudDrive_pb2.SubFilesReply]}, 
    "FindFileByPath": {"argument": CloudDrive_pb2.FindFileByPathRequest, "return": CloudDrive_pb2.CloudDriveFile}, 
    "CreateFolder": {"argument": CloudDrive_pb2.CreateFolderRequest, "return": CloudDrive_pb2.CreateFolderResult}, 
    "RenameFile": {"argument": CloudDrive_pb2.RenameFileRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "RenameFiles": {"argument": CloudDrive_pb2.RenameFilesRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "MoveFile": {"argument": CloudDrive_pb2.MoveFileRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "DeleteFile": {"argument": CloudDrive_pb2.FileRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "DeleteFilePermanently": {"argument": CloudDrive_pb2.FileRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "DeleteFiles": {"argument": CloudDrive_pb2.MultiFileRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "DeleteFilesPermanently": {"argument": CloudDrive_pb2.MultiFileRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "AddOfflineFiles": {"argument": CloudDrive_pb2.AddOfflineFileRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "RemoveOfflineFiles": {"argument": CloudDrive_pb2.RemoveOfflineFilesRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "ListOfflineFilesByPath": {"argument": CloudDrive_pb2.FileRequest, "return": CloudDrive_pb2.OfflineFileListResult}, 
    "ListAllOfflineFiles": {"argument": CloudDrive_pb2.OfflineFileListAllRequest, "return": CloudDrive_pb2.OfflineFileListAllResult}, 
    "GetFileDetailProperties": {"argument": CloudDrive_pb2.FileRequest, "return": CloudDrive_pb2.FileDetailProperties}, 
    "GetSpaceInfo": {"argument": CloudDrive_pb2.FileRequest, "return": CloudDrive_pb2.SpaceInfo}, 
    "GetCloudMemberships": {"argument": CloudDrive_pb2.FileRequest, "return": CloudDrive_pb2.CloudMemberships}, 
    "GetRuntimeInfo": {"return": CloudDrive_pb2.RuntimeInfo}, 
    "GetRunningInfo": {"return": CloudDrive_pb2.RunInfo}, 
    "Logout": {"argument": CloudDrive_pb2.UserLogoutRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "CanAddMoreMountPoints": {"return": CloudDrive_pb2.FileOperationResult}, 
    "GetMountPoints": {"return": CloudDrive_pb2.GetMountPointsResult}, 
    "AddMountPoint": {"argument": CloudDrive_pb2.MountOption, "return": CloudDrive_pb2.MountPointResult}, 
    "RemoveMountPoint": {"argument": CloudDrive_pb2.MountPointRequest, "return": CloudDrive_pb2.MountPointResult}, 
    "Mount": {"argument": CloudDrive_pb2.MountPointRequest, "return": CloudDrive_pb2.MountPointResult}, 
    "Unmount": {"argument": CloudDrive_pb2.MountPointRequest, "return": CloudDrive_pb2.MountPointResult}, 
    "UpdateMountPoint": {"argument": CloudDrive_pb2.UpdateMountPointRequest, "return": CloudDrive_pb2.MountPointResult}, 
    "GetAvailableDriveLetters": {"return": CloudDrive_pb2.GetAvailableDriveLettersResult}, 
    "HasDriveLetters": {"return": CloudDrive_pb2.HasDriveLettersResult}, 
    "LocalGetSubFiles": {"argument": CloudDrive_pb2.LocalGetSubFilesRequest, "return": Iterator[CloudDrive_pb2.LocalGetSubFilesResult]}, 
    "GetAllTasksCount": {"return": CloudDrive_pb2.GetAllTasksCountResult}, 
    "GetDownloadFileCount": {"return": CloudDrive_pb2.GetDownloadFileCountResult}, 
    "GetDownloadFileList": {"return": CloudDrive_pb2.GetDownloadFileListResult}, 
    "GetUploadFileCount": {"return": CloudDrive_pb2.GetUploadFileCountResult}, 
    "GetUploadFileList": {"argument": CloudDrive_pb2.GetUploadFileListRequest, "return": CloudDrive_pb2.GetUploadFileListResult}, 
    "CancelAllUploadFiles": {}, 
    "CancelUploadFiles": {"argument": CloudDrive_pb2.MultpleUploadFileKeyRequest}, 
    "PauseAllUploadFiles": {}, 
    "PauseUploadFiles": {"argument": CloudDrive_pb2.MultpleUploadFileKeyRequest}, 
    "ResumeAllUploadFiles": {}, 
    "ResumeUploadFiles": {"argument": CloudDrive_pb2.MultpleUploadFileKeyRequest}, 
    "CanAddMoreCloudApis": {"return": CloudDrive_pb2.FileOperationResult}, 
    "APILogin115Editthiscookie": {"argument": CloudDrive_pb2.Login115EditthiscookieRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "APILogin115QRCode": {"argument": CloudDrive_pb2.Login115QrCodeRequest, "return": Iterator[CloudDrive_pb2.QRCodeScanMessage]}, 
    "APILoginAliyundriveOAuth": {"argument": CloudDrive_pb2.LoginAliyundriveOAuthRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "APILoginAliyundriveRefreshtoken": {"argument": CloudDrive_pb2.LoginAliyundriveRefreshtokenRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "APILoginAliyunDriveQRCode": {"argument": CloudDrive_pb2.LoginAliyundriveQRCodeRequest, "return": Iterator[CloudDrive_pb2.QRCodeScanMessage]}, 
    "APILoginBaiduPanOAuth": {"argument": CloudDrive_pb2.LoginBaiduPanOAuthRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "APILoginOneDriveOAuth": {"argument": CloudDrive_pb2.LoginOneDriveOAuthRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "ApiLoginGoogleDriveOAuth": {"argument": CloudDrive_pb2.LoginGoogleDriveOAuthRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "ApiLoginGoogleDriveRefreshToken": {"argument": CloudDrive_pb2.LoginGoogleDriveRefreshTokenRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "ApiLoginXunleiOAuth": {"argument": CloudDrive_pb2.LoginXunleiOAuthRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "ApiLogin123panOAuth": {"argument": CloudDrive_pb2.Login123panOAuthRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "APILogin189QRCode": {"return": Iterator[CloudDrive_pb2.QRCodeScanMessage]}, 
    "APILoginPikPak": {"argument": CloudDrive_pb2.UserLoginRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "APILoginWebDav": {"argument": CloudDrive_pb2.LoginWebDavRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "APIAddLocalFolder": {"argument": CloudDrive_pb2.AddLocalFolderRequest, "return": CloudDrive_pb2.APILoginResult}, 
    "RemoveCloudAPI": {"argument": CloudDrive_pb2.RemoveCloudAPIRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "GetAllCloudApis": {"return": CloudDrive_pb2.CloudAPIList}, 
    "GetCloudAPIConfig": {"argument": CloudDrive_pb2.GetCloudAPIConfigRequest, "return": CloudDrive_pb2.CloudAPIConfig}, 
    "SetCloudAPIConfig": {"argument": CloudDrive_pb2.SetCloudAPIConfigRequest}, 
    "GetSystemSettings": {"return": CloudDrive_pb2.SystemSettings}, 
    "SetSystemSettings": {"argument": CloudDrive_pb2.SystemSettings}, 
    "SetDirCacheTimeSecs": {"argument": CloudDrive_pb2.SetDirCacheTimeRequest}, 
    "GetEffectiveDirCacheTimeSecs": {"argument": CloudDrive_pb2.GetEffectiveDirCacheTimeRequest, "return": CloudDrive_pb2.GetEffectiveDirCacheTimeResult}, 
    "GetOpenFileTable": {"argument": CloudDrive_pb2.GetOpenFileTableRequest, "return": CloudDrive_pb2.OpenFileTable}, 
    "GetDirCacheTable": {"return": CloudDrive_pb2.DirCacheTable}, 
    "GetReferencedEntryPaths": {"argument": CloudDrive_pb2.FileRequest, "return": CloudDrive_pb2.StringList}, 
    "GetTempFileTable": {"return": CloudDrive_pb2.TempFileTable}, 
    "PushTaskChange": {"return": Iterator[CloudDrive_pb2.GetAllTasksCountResult]}, 
    "PushMessage": {"return": Iterator[CloudDrive_pb2.CloudDrivePushMessage]}, 
    "GetCloudDrive1UserData": {"return": CloudDrive_pb2.StringResult}, 
    "RestartService": {}, 
    "ShutdownService": {}, 
    "HasUpdate": {"return": CloudDrive_pb2.UpdateResult}, 
    "CheckUpdate": {"return": CloudDrive_pb2.UpdateResult}, 
    "DownloadUpdate": {}, 
    "UpdateSystem": {}, 
    "GetMetaData": {"argument": CloudDrive_pb2.FileRequest, "return": CloudDrive_pb2.FileMetaData}, 
    "GetOriginalPath": {"argument": CloudDrive_pb2.FileRequest, "return": CloudDrive_pb2.StringResult}, 
    "ChangePassword": {"argument": CloudDrive_pb2.ChangePasswordRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "CreateFile": {"argument": CloudDrive_pb2.CreateFileRequest, "return": CloudDrive_pb2.CreateFileResult}, 
    "CloseFile": {"argument": CloudDrive_pb2.CloseFileRequest, "return": CloudDrive_pb2.FileOperationResult}, 
    "WriteToFileStream": {"argument": Iterator[CloudDrive_pb2.WriteFileRequest], "return": CloudDrive_pb2.WriteFileResult}, 
    "WriteToFile": {"argument": CloudDrive_pb2.WriteFileRequest, "return": CloudDrive_pb2.WriteFileResult}, 
    "GetPromotions": {"return": CloudDrive_pb2.GetPromotionsResult}, 
    "UpdatePromotionResult": {}, 
    "GetCloudDrivePlans": {"return": CloudDrive_pb2.GetCloudDrivePlansResult}, 
    "JoinPlan": {"argument": CloudDrive_pb2.JoinPlanRequest, "return": CloudDrive_pb2.JoinPlanResult}, 
    "BindCloudAccount": {"argument": CloudDrive_pb2.BindCloudAccountRequest}, 
    "TransferBalance": {"argument": CloudDrive_pb2.TransferBalanceRequest}, 
    "ChangeEmail": {"argument": CloudDrive_pb2.ChangeUserNameEmailRequest}, 
    "GetBalanceLog": {"return": CloudDrive_pb2.BalanceLogResult}, 
    "CheckActivationCode": {"argument": CloudDrive_pb2.StringValue, "return": CloudDrive_pb2.CheckActivationCodeResult}, 
    "ActivatePlan": {"argument": CloudDrive_pb2.StringValue, "return": CloudDrive_pb2.JoinPlanResult}, 
    "CheckCouponCode": {"argument": CloudDrive_pb2.CheckCouponCodeRequest, "return": CloudDrive_pb2.CouponCodeResult}, 
    "GetReferralCode": {"return": CloudDrive_pb2.StringValue}, 
    "BackupGetAll": {"return": CloudDrive_pb2.BackupList}, 
    "BackupAdd": {"argument": CloudDrive_pb2.Backup}, 
    "BackupRemove": {"argument": CloudDrive_pb2.StringValue}, 
    "BackupUpdate": {"argument": CloudDrive_pb2.Backup}, 
    "BackupAddDestination": {"argument": CloudDrive_pb2.BackupModifyRequest}, 
    "BackupRemoveDestination": {"argument": CloudDrive_pb2.BackupModifyRequest}, 
    "BackupSetEnabled": {"argument": CloudDrive_pb2.BackupSetEnabledRequest}, 
    "BackupSetFileSystemWatchEnabled": {"argument": CloudDrive_pb2.BackupModifyRequest}, 
    "BackupUpdateStrategies": {"argument": CloudDrive_pb2.BackupModifyRequest}, 
    "BackupRestartWalkingThrough": {"argument": CloudDrive_pb2.StringValue}, 
    "CanAddMoreBackups": {"return": CloudDrive_pb2.FileOperationResult}, 
    "GetMachineId": {"return": CloudDrive_pb2.StringResult}, 
    "GetOnlineDevices": {"return": CloudDrive_pb2.OnlineDevices}, 
    "KickoutDevice": {"argument": CloudDrive_pb2.DeviceRequest}, 
}


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
    def stub(self, /) -> CloudDrive_pb2_grpc.CloudDriveFileSrvStub:
        return CloudDrive_pb2_grpc.CloudDriveFileSrvStub(self.channel)

    @cached_property
    def async_channel(self, /) -> AsyncChannel:
        origin = self.origin
        return AsyncChannel(origin.host, origin.port)

    @cached_property
    def async_stub(self, /) -> CloudDrive_grpc.CloudDriveFileSrvStub:
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
        response = self.stub.GetToken(CloudDrive_pb2.GetTokenRequest(userName=username, password=password))
        self.metadata[:] = [("authorization", "Bearer " + response.token),]

    def GetSystemInfo(self, /, async_: bool = False) -> CloudDrive_pb2.CloudDriveSystemInfo:
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
        return (self.async_stub if async_ else self.stub).GetSystemInfo(Empty(), metadata=self.metadata)

    def GetToken(self, arg: CloudDrive_pb2.GetTokenRequest, /, async_: bool = False) -> CloudDrive_pb2.JWTToken:
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
        return (self.async_stub if async_ else self.stub).GetToken(arg, metadata=self.metadata)

    def Login(self, arg: CloudDrive_pb2.UserLoginRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).Login(arg, metadata=self.metadata)

    def Register(self, arg: CloudDrive_pb2.UserRegisterRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).Register(arg, metadata=self.metadata)

    def SendResetAccountEmail(self, arg: CloudDrive_pb2.SendResetAccountEmailRequest, /, async_: bool = False) -> None:
        """
        asks cloudfs server to send reset account email with reset link

        ------------------- protobuf rpc definition --------------------

        // asks cloudfs server to send reset account email with reset link
        rpc SendResetAccountEmail(SendResetAccountEmailRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message SendResetAccountEmailRequest { string email = 1; }
        """
        return (self.async_stub if async_ else self.stub).SendResetAccountEmail(arg, metadata=self.metadata)

    def ResetAccount(self, arg: CloudDrive_pb2.ResetAccountRequest, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).ResetAccount(arg, metadata=self.metadata)

    def SendConfirmEmail(self, /, async_: bool = False) -> None:
        """
        authorized methods, Authorization header with Bearer {token} is requirerd
        asks cloudfs server to send confirm email with confirm link

        ------------------- protobuf rpc definition --------------------

        // authorized methods, Authorization header with Bearer {token} is requirerd
        // asks cloudfs server to send confirm email with confirm link
        rpc SendConfirmEmail(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        return (self.async_stub if async_ else self.stub).SendConfirmEmail(Empty(), metadata=self.metadata)

    def ConfirmEmail(self, arg: CloudDrive_pb2.ConfirmEmailRequest, /, async_: bool = False) -> None:
        """
        confirm email by confirm code

        ------------------- protobuf rpc definition --------------------

        // confirm email by confirm code
        rpc ConfirmEmail(ConfirmEmailRequest) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message ConfirmEmailRequest { string confirmCode = 1; }
        """
        return (self.async_stub if async_ else self.stub).ConfirmEmail(arg, metadata=self.metadata)

    def GetAccountStatus(self, /, async_: bool = False) -> CloudDrive_pb2.AccountStatusResult:
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
        }
        """
        return (self.async_stub if async_ else self.stub).GetAccountStatus(Empty(), metadata=self.metadata)

    def GetSubFiles(self, arg: CloudDrive_pb2.ListSubFileRequest, /, async_: bool = False) -> Iterator[CloudDrive_pb2.SubFilesReply]:
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
        }
        message ListSubFileRequest {
          string path = 1;
          bool forceRefresh = 2;
          optional bool checkExpires = 3;
        }
        message SubFilesReply { repeated CloudDriveFile subFiles = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetSubFiles(arg, metadata=self.metadata)

    def GetSearchResults(self, arg: CloudDrive_pb2.SearchRequest, /, async_: bool = False) -> Iterator[CloudDrive_pb2.SubFilesReply]:
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
        }
        message SearchRequest {
          string path = 1;
          string searchFor = 2;
          bool forceRefresh = 3;
          bool fuzzyMatch = 4;
        }
        message SubFilesReply { repeated CloudDriveFile subFiles = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetSearchResults(arg, metadata=self.metadata)

    def FindFileByPath(self, arg: CloudDrive_pb2.FindFileByPathRequest, /, async_: bool = False) -> CloudDrive_pb2.CloudDriveFile:
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
        return (self.async_stub if async_ else self.stub).FindFileByPath(arg, metadata=self.metadata)

    def CreateFolder(self, arg: CloudDrive_pb2.CreateFolderRequest, /, async_: bool = False) -> CloudDrive_pb2.CreateFolderResult:
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
        return (self.async_stub if async_ else self.stub).CreateFolder(arg, metadata=self.metadata)

    def RenameFile(self, arg: CloudDrive_pb2.RenameFileRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).RenameFile(arg, metadata=self.metadata)

    def RenameFiles(self, arg: CloudDrive_pb2.RenameFilesRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).RenameFiles(arg, metadata=self.metadata)

    def MoveFile(self, arg: CloudDrive_pb2.MoveFileRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
          repeated string theFilePaths = 1;
          string destPath = 2;
        }
        """
        return (self.async_stub if async_ else self.stub).MoveFile(arg, metadata=self.metadata)

    def DeleteFile(self, arg: CloudDrive_pb2.FileRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).DeleteFile(arg, metadata=self.metadata)

    def DeleteFilePermanently(self, arg: CloudDrive_pb2.FileRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).DeleteFilePermanently(arg, metadata=self.metadata)

    def DeleteFiles(self, arg: CloudDrive_pb2.MultiFileRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).DeleteFiles(arg, metadata=self.metadata)

    def DeleteFilesPermanently(self, arg: CloudDrive_pb2.MultiFileRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).DeleteFilesPermanently(arg, metadata=self.metadata)

    def AddOfflineFiles(self, arg: CloudDrive_pb2.AddOfflineFileRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
        """
        add offline files by providing magnet, sha1, ..., applies only with folders
        with canOfflineDownload is tru

        ------------------- protobuf rpc definition --------------------

        // add offline files by providing magnet, sha1, ..., applies only with folders
        // with canOfflineDownload is tru
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
        return (self.async_stub if async_ else self.stub).AddOfflineFiles(arg, metadata=self.metadata)

    def RemoveOfflineFiles(self, arg: CloudDrive_pb2.RemoveOfflineFilesRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).RemoveOfflineFiles(arg, metadata=self.metadata)

    def ListOfflineFilesByPath(self, arg: CloudDrive_pb2.FileRequest, /, async_: bool = False) -> CloudDrive_pb2.OfflineFileListResult:
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
        return (self.async_stub if async_ else self.stub).ListOfflineFilesByPath(arg, metadata=self.metadata)

    def ListAllOfflineFiles(self, arg: CloudDrive_pb2.OfflineFileListAllRequest, /, async_: bool = False) -> CloudDrive_pb2.OfflineFileListAllResult:
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
        return (self.async_stub if async_ else self.stub).ListAllOfflineFiles(arg, metadata=self.metadata)

    def GetFileDetailProperties(self, arg: CloudDrive_pb2.FileRequest, /, async_: bool = False) -> CloudDrive_pb2.FileDetailProperties:
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
        return (self.async_stub if async_ else self.stub).GetFileDetailProperties(arg, metadata=self.metadata)

    def GetSpaceInfo(self, arg: CloudDrive_pb2.FileRequest, /, async_: bool = False) -> CloudDrive_pb2.SpaceInfo:
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
        return (self.async_stub if async_ else self.stub).GetSpaceInfo(arg, metadata=self.metadata)

    def GetCloudMemberships(self, arg: CloudDrive_pb2.FileRequest, /, async_: bool = False) -> CloudDrive_pb2.CloudMemberships:
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
        return (self.async_stub if async_ else self.stub).GetCloudMemberships(arg, metadata=self.metadata)

    def GetRuntimeInfo(self, /, async_: bool = False) -> CloudDrive_pb2.RuntimeInfo:
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
        return (self.async_stub if async_ else self.stub).GetRuntimeInfo(Empty(), metadata=self.metadata)

    def GetRunningInfo(self, /, async_: bool = False) -> CloudDrive_pb2.RunInfo:
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
        }
        """
        return (self.async_stub if async_ else self.stub).GetRunningInfo(Empty(), metadata=self.metadata)

    def Logout(self, arg: CloudDrive_pb2.UserLogoutRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).Logout(arg, metadata=self.metadata)

    def CanAddMoreMountPoints(self, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).CanAddMoreMountPoints(Empty(), metadata=self.metadata)

    def GetMountPoints(self, /, async_: bool = False) -> CloudDrive_pb2.GetMountPointsResult:
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
        return (self.async_stub if async_ else self.stub).GetMountPoints(Empty(), metadata=self.metadata)

    def AddMountPoint(self, arg: CloudDrive_pb2.MountOption, /, async_: bool = False) -> CloudDrive_pb2.MountPointResult:
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
        return (self.async_stub if async_ else self.stub).AddMountPoint(arg, metadata=self.metadata)

    def RemoveMountPoint(self, arg: CloudDrive_pb2.MountPointRequest, /, async_: bool = False) -> CloudDrive_pb2.MountPointResult:
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
        return (self.async_stub if async_ else self.stub).RemoveMountPoint(arg, metadata=self.metadata)

    def Mount(self, arg: CloudDrive_pb2.MountPointRequest, /, async_: bool = False) -> CloudDrive_pb2.MountPointResult:
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
        return (self.async_stub if async_ else self.stub).Mount(arg, metadata=self.metadata)

    def Unmount(self, arg: CloudDrive_pb2.MountPointRequest, /, async_: bool = False) -> CloudDrive_pb2.MountPointResult:
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
        return (self.async_stub if async_ else self.stub).Unmount(arg, metadata=self.metadata)

    def UpdateMountPoint(self, arg: CloudDrive_pb2.UpdateMountPointRequest, /, async_: bool = False) -> CloudDrive_pb2.MountPointResult:
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
        return (self.async_stub if async_ else self.stub).UpdateMountPoint(arg, metadata=self.metadata)

    def GetAvailableDriveLetters(self, /, async_: bool = False) -> CloudDrive_pb2.GetAvailableDriveLettersResult:
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
        return (self.async_stub if async_ else self.stub).GetAvailableDriveLetters(Empty(), metadata=self.metadata)

    def HasDriveLetters(self, /, async_: bool = False) -> CloudDrive_pb2.HasDriveLettersResult:
        """
        check if server has driver letters, returns true only on windows

        ------------------- protobuf rpc definition --------------------

        // check if server has driver letters, returns true only on windows
        rpc HasDriveLetters(google.protobuf.Empty) returns (HasDriveLettersResult) {}

        ------------------- protobuf type definition -------------------

        message HasDriveLettersResult { bool hasDriveLetters = 1; }
        """
        return (self.async_stub if async_ else self.stub).HasDriveLetters(Empty(), metadata=self.metadata)

    def LocalGetSubFiles(self, arg: CloudDrive_pb2.LocalGetSubFilesRequest, /, async_: bool = False) -> Iterator[CloudDrive_pb2.LocalGetSubFilesResult]:
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
        return (self.async_stub if async_ else self.stub).LocalGetSubFiles(arg, metadata=self.metadata)

    def GetAllTasksCount(self, /, async_: bool = False) -> CloudDrive_pb2.GetAllTasksCountResult:
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
        return (self.async_stub if async_ else self.stub).GetAllTasksCount(Empty(), metadata=self.metadata)

    def GetDownloadFileCount(self, /, async_: bool = False) -> CloudDrive_pb2.GetDownloadFileCountResult:
        """
        get download tasks' count

        ------------------- protobuf rpc definition --------------------

        // get download tasks' count
        rpc GetDownloadFileCount(google.protobuf.Empty)
            returns (GetDownloadFileCountResult) {}

        ------------------- protobuf type definition -------------------

        message GetDownloadFileCountResult { uint32 fileCount = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetDownloadFileCount(Empty(), metadata=self.metadata)

    def GetDownloadFileList(self, /, async_: bool = False) -> CloudDrive_pb2.GetDownloadFileListResult:
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
        }
        message GetDownloadFileListResult {
          double globalBytesPerSecond = 1;
          repeated DownloadFileInfo downloadFiles = 4;
        }
        """
        return (self.async_stub if async_ else self.stub).GetDownloadFileList(Empty(), metadata=self.metadata)

    def GetUploadFileCount(self, /, async_: bool = False) -> CloudDrive_pb2.GetUploadFileCountResult:
        """
        get all upload tasks' count

        ------------------- protobuf rpc definition --------------------

        // get all upload tasks' count
        rpc GetUploadFileCount(google.protobuf.Empty)
            returns (GetUploadFileCountResult) {}

        ------------------- protobuf type definition -------------------

        message GetUploadFileCountResult { uint32 fileCount = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetUploadFileCount(Empty(), metadata=self.metadata)

    def GetUploadFileList(self, arg: CloudDrive_pb2.GetUploadFileListRequest, /, async_: bool = False) -> CloudDrive_pb2.GetUploadFileListResult:
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
        return (self.async_stub if async_ else self.stub).GetUploadFileList(arg, metadata=self.metadata)

    def CancelAllUploadFiles(self, /, async_: bool = False) -> None:
        """
        cancel all upload tasks

        ------------------- protobuf rpc definition --------------------

        // cancel all upload tasks
        rpc CancelAllUploadFiles(google.protobuf.Empty)
            returns (google.protobuf.Empty) {}
        """
        return (self.async_stub if async_ else self.stub).CancelAllUploadFiles(Empty(), metadata=self.metadata)

    def CancelUploadFiles(self, arg: CloudDrive_pb2.MultpleUploadFileKeyRequest, /, async_: bool = False) -> None:
        """
        cancel selected upload tasks

        ------------------- protobuf rpc definition --------------------

        // cancel selected upload tasks
        rpc CancelUploadFiles(MultpleUploadFileKeyRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message MultpleUploadFileKeyRequest { repeated string keys = 1; }
        """
        return (self.async_stub if async_ else self.stub).CancelUploadFiles(arg, metadata=self.metadata)

    def PauseAllUploadFiles(self, /, async_: bool = False) -> None:
        """
        pause all upload tasks

        ------------------- protobuf rpc definition --------------------

        // pause all upload tasks
        rpc PauseAllUploadFiles(google.protobuf.Empty)
            returns (google.protobuf.Empty) {}
        """
        return (self.async_stub if async_ else self.stub).PauseAllUploadFiles(Empty(), metadata=self.metadata)

    def PauseUploadFiles(self, arg: CloudDrive_pb2.MultpleUploadFileKeyRequest, /, async_: bool = False) -> None:
        """
        pause selected upload tasks

        ------------------- protobuf rpc definition --------------------

        // pause selected upload tasks
        rpc PauseUploadFiles(MultpleUploadFileKeyRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message MultpleUploadFileKeyRequest { repeated string keys = 1; }
        """
        return (self.async_stub if async_ else self.stub).PauseUploadFiles(arg, metadata=self.metadata)

    def ResumeAllUploadFiles(self, /, async_: bool = False) -> None:
        """
        resume all upload tasks

        ------------------- protobuf rpc definition --------------------

        // resume all upload tasks
        rpc ResumeAllUploadFiles(google.protobuf.Empty)
            returns (google.protobuf.Empty) {}
        """
        return (self.async_stub if async_ else self.stub).ResumeAllUploadFiles(Empty(), metadata=self.metadata)

    def ResumeUploadFiles(self, arg: CloudDrive_pb2.MultpleUploadFileKeyRequest, /, async_: bool = False) -> None:
        """
        resume selected upload tasks

        ------------------- protobuf rpc definition --------------------

        // resume selected upload tasks
        rpc ResumeUploadFiles(MultpleUploadFileKeyRequest)
            returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message MultpleUploadFileKeyRequest { repeated string keys = 1; }
        """
        return (self.async_stub if async_ else self.stub).ResumeUploadFiles(arg, metadata=self.metadata)

    def CanAddMoreCloudApis(self, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).CanAddMoreCloudApis(Empty(), metadata=self.metadata)

    def APILogin115Editthiscookie(self, arg: CloudDrive_pb2.Login115EditthiscookieRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
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
        return (self.async_stub if async_ else self.stub).APILogin115Editthiscookie(arg, metadata=self.metadata)

    def APILogin115QRCode(self, arg: CloudDrive_pb2.Login115QrCodeRequest, /, async_: bool = False) -> Iterator[CloudDrive_pb2.QRCodeScanMessage]:
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
        return (self.async_stub if async_ else self.stub).APILogin115QRCode(arg, metadata=self.metadata)

    def APILoginAliyundriveOAuth(self, arg: CloudDrive_pb2.LoginAliyundriveOAuthRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
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
        return (self.async_stub if async_ else self.stub).APILoginAliyundriveOAuth(arg, metadata=self.metadata)

    def APILoginAliyundriveRefreshtoken(self, arg: CloudDrive_pb2.LoginAliyundriveRefreshtokenRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
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
        return (self.async_stub if async_ else self.stub).APILoginAliyundriveRefreshtoken(arg, metadata=self.metadata)

    def APILoginAliyunDriveQRCode(self, arg: CloudDrive_pb2.LoginAliyundriveQRCodeRequest, /, async_: bool = False) -> Iterator[CloudDrive_pb2.QRCodeScanMessage]:
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
        return (self.async_stub if async_ else self.stub).APILoginAliyunDriveQRCode(arg, metadata=self.metadata)

    def APILoginBaiduPanOAuth(self, arg: CloudDrive_pb2.LoginBaiduPanOAuthRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
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
        return (self.async_stub if async_ else self.stub).APILoginBaiduPanOAuth(arg, metadata=self.metadata)

    def APILoginOneDriveOAuth(self, arg: CloudDrive_pb2.LoginOneDriveOAuthRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
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
        return (self.async_stub if async_ else self.stub).APILoginOneDriveOAuth(arg, metadata=self.metadata)

    def ApiLoginGoogleDriveOAuth(self, arg: CloudDrive_pb2.LoginGoogleDriveOAuthRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
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
        return (self.async_stub if async_ else self.stub).ApiLoginGoogleDriveOAuth(arg, metadata=self.metadata)

    def ApiLoginGoogleDriveRefreshToken(self, arg: CloudDrive_pb2.LoginGoogleDriveRefreshTokenRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
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
        return (self.async_stub if async_ else self.stub).ApiLoginGoogleDriveRefreshToken(arg, metadata=self.metadata)

    def ApiLoginXunleiOAuth(self, arg: CloudDrive_pb2.LoginXunleiOAuthRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
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
        return (self.async_stub if async_ else self.stub).ApiLoginXunleiOAuth(arg, metadata=self.metadata)

    def ApiLogin123panOAuth(self, arg: CloudDrive_pb2.Login123panOAuthRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
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
        return (self.async_stub if async_ else self.stub).ApiLogin123panOAuth(arg, metadata=self.metadata)

    def APILogin189QRCode(self, /, async_: bool = False) -> Iterator[CloudDrive_pb2.QRCodeScanMessage]:
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
        return (self.async_stub if async_ else self.stub).APILogin189QRCode(Empty(), metadata=self.metadata)

    def APILoginPikPak(self, arg: CloudDrive_pb2.UserLoginRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
        """
        add PikPak cloud with username and password

        ------------------- protobuf rpc definition --------------------

        // add PikPak cloud with username and password
        rpc APILoginPikPak(UserLoginRequest) returns (APILoginResult) {}

        ------------------- protobuf type definition -------------------

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message UserLoginRequest {
          string userName = 1;
          string password = 2;
          bool synDataToCloud = 3;
        }
        """
        return (self.async_stub if async_ else self.stub).APILoginPikPak(arg, metadata=self.metadata)

    def APILoginWebDav(self, arg: CloudDrive_pb2.LoginWebDavRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
        """
        add webdav

        ------------------- protobuf rpc definition --------------------

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
        return (self.async_stub if async_ else self.stub).APILoginWebDav(arg, metadata=self.metadata)

    def APIAddLocalFolder(self, arg: CloudDrive_pb2.AddLocalFolderRequest, /, async_: bool = False) -> CloudDrive_pb2.APILoginResult:
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
        return (self.async_stub if async_ else self.stub).APIAddLocalFolder(arg, metadata=self.metadata)

    def RemoveCloudAPI(self, arg: CloudDrive_pb2.RemoveCloudAPIRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).RemoveCloudAPI(arg, metadata=self.metadata)

    def GetAllCloudApis(self, /, async_: bool = False) -> CloudDrive_pb2.CloudAPIList:
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
        }
        message CloudAPIList { repeated CloudAPI apis = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetAllCloudApis(Empty(), metadata=self.metadata)

    def GetCloudAPIConfig(self, arg: CloudDrive_pb2.GetCloudAPIConfigRequest, /, async_: bool = False) -> CloudDrive_pb2.CloudAPIConfig:
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
        return (self.async_stub if async_ else self.stub).GetCloudAPIConfig(arg, metadata=self.metadata)

    def SetCloudAPIConfig(self, arg: CloudDrive_pb2.SetCloudAPIConfigRequest, /, async_: bool = False) -> None:
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
        }
        message SetCloudAPIConfigRequest {
          string cloudName = 1;
          string userName = 2;
          CloudAPIConfig config = 3;
        }
        """
        return (self.async_stub if async_ else self.stub).SetCloudAPIConfig(arg, metadata=self.metadata)

    def GetSystemSettings(self, /, async_: bool = False) -> CloudDrive_pb2.SystemSettings:
        """
        get all system setings value

        ------------------- protobuf rpc definition --------------------

        // get all system setings value
        rpc GetSystemSettings(google.protobuf.Empty) returns (SystemSettings) {}

        ------------------- protobuf type definition -------------------

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
        }
        enum UpdateChannel {
          Release = 0;
          Beta = 1;
        }
        """
        return (self.async_stub if async_ else self.stub).GetSystemSettings(Empty(), metadata=self.metadata)

    def SetSystemSettings(self, arg: CloudDrive_pb2.SystemSettings, /, async_: bool = False) -> None:
        """
        set selected system settings value

        ------------------- protobuf rpc definition --------------------

        // set selected system settings value
        rpc SetSystemSettings(SystemSettings) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

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
        }
        enum UpdateChannel {
          Release = 0;
          Beta = 1;
        }
        """
        return (self.async_stub if async_ else self.stub).SetSystemSettings(arg, metadata=self.metadata)

    def SetDirCacheTimeSecs(self, arg: CloudDrive_pb2.SetDirCacheTimeRequest, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).SetDirCacheTimeSecs(arg, metadata=self.metadata)

    def GetEffectiveDirCacheTimeSecs(self, arg: CloudDrive_pb2.GetEffectiveDirCacheTimeRequest, /, async_: bool = False) -> CloudDrive_pb2.GetEffectiveDirCacheTimeResult:
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
        return (self.async_stub if async_ else self.stub).GetEffectiveDirCacheTimeSecs(arg, metadata=self.metadata)

    def GetOpenFileTable(self, arg: CloudDrive_pb2.GetOpenFileTableRequest, /, async_: bool = False) -> CloudDrive_pb2.OpenFileTable:
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
        return (self.async_stub if async_ else self.stub).GetOpenFileTable(arg, metadata=self.metadata)

    def GetDirCacheTable(self, /, async_: bool = False) -> CloudDrive_pb2.DirCacheTable:
        """
        get dir cache table

        ------------------- protobuf rpc definition --------------------

        // get dir cache table
        rpc GetDirCacheTable(google.protobuf.Empty) returns (DirCacheTable) {}

        ------------------- protobuf type definition -------------------

        message DirCacheTable { map<string, DirCacheItem> dirCacheTable = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetDirCacheTable(Empty(), metadata=self.metadata)

    def GetReferencedEntryPaths(self, arg: CloudDrive_pb2.FileRequest, /, async_: bool = False) -> CloudDrive_pb2.StringList:
        """
        get referenced entry paths of parent path

        ------------------- protobuf rpc definition --------------------

        // get referenced entry paths of parent path
        rpc GetReferencedEntryPaths(FileRequest) returns (StringList) {}

        ------------------- protobuf type definition -------------------

        message FileRequest { string path = 1; }
        message StringList { repeated string values = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetReferencedEntryPaths(arg, metadata=self.metadata)

    def GetTempFileTable(self, /, async_: bool = False) -> CloudDrive_pb2.TempFileTable:
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
        return (self.async_stub if async_ else self.stub).GetTempFileTable(Empty(), metadata=self.metadata)

    def PushTaskChange(self, /, async_: bool = False) -> Iterator[CloudDrive_pb2.GetAllTasksCountResult]:
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
        return (self.async_stub if async_ else self.stub).PushTaskChange(Empty(), metadata=self.metadata)

    def PushMessage(self, /, async_: bool = False) -> Iterator[CloudDrive_pb2.CloudDrivePushMessage]:
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
          }
          MessageType messageType = 1;
          oneof data {
            TransferTaskStatus transferTaskStatus = 2;
            UpdateStatus updateStatus = 3;
            ExitedMessage exitedMessage = 4;
            FileSystemChangeList fileSystemChanges = 5;
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
        message FileSystemChangeList {
          repeated FileSystemChange fileSystemChanges = 1;
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
        return (self.async_stub if async_ else self.stub).PushMessage(Empty(), metadata=self.metadata)

    def GetCloudDrive1UserData(self, /, async_: bool = False) -> CloudDrive_pb2.StringResult:
        """
        get CloudDrive1's user data string

        ------------------- protobuf rpc definition --------------------

        // get CloudDrive1's user data string
        rpc GetCloudDrive1UserData(google.protobuf.Empty) returns (StringResult) {}

        ------------------- protobuf type definition -------------------

        message StringResult { string result = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetCloudDrive1UserData(Empty(), metadata=self.metadata)

    def RestartService(self, /, async_: bool = False) -> None:
        """
        restart service

        ------------------- protobuf rpc definition --------------------

        // restart service
        rpc RestartService(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        return (self.async_stub if async_ else self.stub).RestartService(Empty(), metadata=self.metadata)

    def ShutdownService(self, /, async_: bool = False) -> None:
        """
        shutdown service

        ------------------- protobuf rpc definition --------------------

        // shutdown service
        rpc ShutdownService(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        return (self.async_stub if async_ else self.stub).ShutdownService(Empty(), metadata=self.metadata)

    def HasUpdate(self, /, async_: bool = False) -> CloudDrive_pb2.UpdateResult:
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
        return (self.async_stub if async_ else self.stub).HasUpdate(Empty(), metadata=self.metadata)

    def CheckUpdate(self, /, async_: bool = False) -> CloudDrive_pb2.UpdateResult:
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
        return (self.async_stub if async_ else self.stub).CheckUpdate(Empty(), metadata=self.metadata)

    def DownloadUpdate(self, /, async_: bool = False) -> None:
        """
        download newest version

        ------------------- protobuf rpc definition --------------------

        // download newest version
        rpc DownloadUpdate(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        return (self.async_stub if async_ else self.stub).DownloadUpdate(Empty(), metadata=self.metadata)

    def UpdateSystem(self, /, async_: bool = False) -> None:
        """
        update to newest version

        ------------------- protobuf rpc definition --------------------

        // update to newest version
        rpc UpdateSystem(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        return (self.async_stub if async_ else self.stub).UpdateSystem(Empty(), metadata=self.metadata)

    def GetMetaData(self, arg: CloudDrive_pb2.FileRequest, /, async_: bool = False) -> CloudDrive_pb2.FileMetaData:
        """
        get file metadata

        ------------------- protobuf rpc definition --------------------

        // get file metadata
        rpc GetMetaData(FileRequest) returns (FileMetaData) {}

        ------------------- protobuf type definition -------------------

        message FileMetaData { map<string, string> metadata = 1; }
        message FileRequest { string path = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetMetaData(arg, metadata=self.metadata)

    def GetOriginalPath(self, arg: CloudDrive_pb2.FileRequest, /, async_: bool = False) -> CloudDrive_pb2.StringResult:
        """
        get file's original path from search result

        ------------------- protobuf rpc definition --------------------

        // get file's original path from search result
        rpc GetOriginalPath(FileRequest) returns (StringResult) {}

        ------------------- protobuf type definition -------------------

        message FileRequest { string path = 1; }
        message StringResult { string result = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetOriginalPath(arg, metadata=self.metadata)

    def ChangePassword(self, arg: CloudDrive_pb2.ChangePasswordRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).ChangePassword(arg, metadata=self.metadata)

    def CreateFile(self, arg: CloudDrive_pb2.CreateFileRequest, /, async_: bool = False) -> CloudDrive_pb2.CreateFileResult:
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
        return (self.async_stub if async_ else self.stub).CreateFile(arg, metadata=self.metadata)

    def CloseFile(self, arg: CloudDrive_pb2.CloseFileRequest, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).CloseFile(arg, metadata=self.metadata)

    def WriteToFileStream(self, arg: Iterator[CloudDrive_pb2.WriteFileRequest], /, async_: bool = False) -> CloudDrive_pb2.WriteFileResult:
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
        return (self.async_stub if async_ else self.stub).WriteToFileStream(arg, metadata=self.metadata)

    def WriteToFile(self, arg: CloudDrive_pb2.WriteFileRequest, /, async_: bool = False) -> CloudDrive_pb2.WriteFileResult:
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
        return (self.async_stub if async_ else self.stub).WriteToFile(arg, metadata=self.metadata)

    def GetPromotions(self, /, async_: bool = False) -> CloudDrive_pb2.GetPromotionsResult:
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
        return (self.async_stub if async_ else self.stub).GetPromotions(Empty(), metadata=self.metadata)

    def UpdatePromotionResult(self, /, async_: bool = False) -> None:
        """
        update promotion result after purchased

        ------------------- protobuf rpc definition --------------------

        // update promotion result after purchased
        rpc UpdatePromotionResult(google.protobuf.Empty)
            returns (google.protobuf.Empty) {}
        """
        return (self.async_stub if async_ else self.stub).UpdatePromotionResult(Empty(), metadata=self.metadata)

    def GetCloudDrivePlans(self, /, async_: bool = False) -> CloudDrive_pb2.GetCloudDrivePlansResult:
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
        }
        message GetCloudDrivePlansResult { repeated CloudDrivePlan plans = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetCloudDrivePlans(Empty(), metadata=self.metadata)

    def JoinPlan(self, arg: CloudDrive_pb2.JoinPlanRequest, /, async_: bool = False) -> CloudDrive_pb2.JoinPlanResult:
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
        }
        """
        return (self.async_stub if async_ else self.stub).JoinPlan(arg, metadata=self.metadata)

    def BindCloudAccount(self, arg: CloudDrive_pb2.BindCloudAccountRequest, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).BindCloudAccount(arg, metadata=self.metadata)

    def TransferBalance(self, arg: CloudDrive_pb2.TransferBalanceRequest, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).TransferBalance(arg, metadata=self.metadata)

    def ChangeEmail(self, arg: CloudDrive_pb2.ChangeUserNameEmailRequest, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).ChangeEmail(arg, metadata=self.metadata)

    def GetBalanceLog(self, /, async_: bool = False) -> CloudDrive_pb2.BalanceLogResult:
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
        return (self.async_stub if async_ else self.stub).GetBalanceLog(Empty(), metadata=self.metadata)

    def CheckActivationCode(self, arg: CloudDrive_pb2.StringValue, /, async_: bool = False) -> CloudDrive_pb2.CheckActivationCodeResult:
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
        return (self.async_stub if async_ else self.stub).CheckActivationCode(arg, metadata=self.metadata)

    def ActivatePlan(self, arg: CloudDrive_pb2.StringValue, /, async_: bool = False) -> CloudDrive_pb2.JoinPlanResult:
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
        }
        message StringValue { string value = 1; }
        """
        return (self.async_stub if async_ else self.stub).ActivatePlan(arg, metadata=self.metadata)

    def CheckCouponCode(self, arg: CloudDrive_pb2.CheckCouponCodeRequest, /, async_: bool = False) -> CloudDrive_pb2.CouponCodeResult:
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
        return (self.async_stub if async_ else self.stub).CheckCouponCode(arg, metadata=self.metadata)

    def GetReferralCode(self, /, async_: bool = False) -> CloudDrive_pb2.StringValue:
        """
        get referral code of current user

        ------------------- protobuf rpc definition --------------------

        // get referral code of current user
        rpc GetReferralCode(google.protobuf.Empty) returns (StringValue) {}

        ------------------- protobuf type definition -------------------

        message StringValue { string value = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetReferralCode(Empty(), metadata=self.metadata)

    def BackupGetAll(self, /, async_: bool = False) -> CloudDrive_pb2.BackupList:
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
        return (self.async_stub if async_ else self.stub).BackupGetAll(Empty(), metadata=self.metadata)

    def BackupAdd(self, arg: CloudDrive_pb2.Backup, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).BackupAdd(arg, metadata=self.metadata)

    def BackupRemove(self, arg: CloudDrive_pb2.StringValue, /, async_: bool = False) -> None:
        """
        remove a backup by it's source path

        ------------------- protobuf rpc definition --------------------

        // remove a backup by it's source path
        rpc BackupRemove(StringValue) returns (google.protobuf.Empty) {}

        ------------------- protobuf type definition -------------------

        message StringValue { string value = 1; }
        """
        return (self.async_stub if async_ else self.stub).BackupRemove(arg, metadata=self.metadata)

    def BackupUpdate(self, arg: CloudDrive_pb2.Backup, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).BackupUpdate(arg, metadata=self.metadata)

    def BackupAddDestination(self, arg: CloudDrive_pb2.BackupModifyRequest, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).BackupAddDestination(arg, metadata=self.metadata)

    def BackupRemoveDestination(self, arg: CloudDrive_pb2.BackupModifyRequest, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).BackupRemoveDestination(arg, metadata=self.metadata)

    def BackupSetEnabled(self, arg: CloudDrive_pb2.BackupSetEnabledRequest, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).BackupSetEnabled(arg, metadata=self.metadata)

    def BackupSetFileSystemWatchEnabled(self, arg: CloudDrive_pb2.BackupModifyRequest, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).BackupSetFileSystemWatchEnabled(arg, metadata=self.metadata)

    def BackupUpdateStrategies(self, arg: CloudDrive_pb2.BackupModifyRequest, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).BackupUpdateStrategies(arg, metadata=self.metadata)

    def BackupRestartWalkingThrough(self, arg: CloudDrive_pb2.StringValue, /, async_: bool = False) -> None:
        """
        restart a backup walking through

        ------------------- protobuf rpc definition --------------------

        // restart a backup walking through
        rpc BackupRestartWalkingThrough(StringValue) returns (google.protobuf.Empty) {
        }

        ------------------- protobuf type definition -------------------

        message StringValue { string value = 1; }
        """
        return (self.async_stub if async_ else self.stub).BackupRestartWalkingThrough(arg, metadata=self.metadata)

    def CanAddMoreBackups(self, /, async_: bool = False) -> CloudDrive_pb2.FileOperationResult:
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
        return (self.async_stub if async_ else self.stub).CanAddMoreBackups(Empty(), metadata=self.metadata)

    def GetMachineId(self, /, async_: bool = False) -> CloudDrive_pb2.StringResult:
        """
        get machine id

        ------------------- protobuf rpc definition --------------------

        // get machine id
        rpc GetMachineId(google.protobuf.Empty) returns (StringResult) {}

        ------------------- protobuf type definition -------------------

        message StringResult { string result = 1; }
        """
        return (self.async_stub if async_ else self.stub).GetMachineId(Empty(), metadata=self.metadata)

    def GetOnlineDevices(self, /, async_: bool = False) -> CloudDrive_pb2.OnlineDevices:
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
        return (self.async_stub if async_ else self.stub).GetOnlineDevices(Empty(), metadata=self.metadata)

    def KickoutDevice(self, arg: CloudDrive_pb2.DeviceRequest, /, async_: bool = False) -> None:
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
        return (self.async_stub if async_ else self.stub).KickoutDevice(arg, metadata=self.metadata)

