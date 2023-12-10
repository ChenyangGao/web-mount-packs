#!/usr/bin/env python3
# encoding: utf-8

__author__ = "ChenyangGao <https://chenyanggao.github.io/>"
__all__ = ["Client"]

from urllib.parse import urlsplit
from typing import Iterator

from google.protobuf.empty_pb2 import Empty # type: ignore
from grpc import insecure_channel # type: ignore

import pathlib, sys
PROTO_DIR = str(pathlib.Path(__file__).parent / "proto")
if PROTO_DIR not in sys.path:
    sys.path.append(PROTO_DIR)

import CloudDrive_pb2 # type: ignore
import CloudDrive_pb2_grpc # type: ignore


class Client:
    "clouddrive client that encapsulates grpc APIs"
    def __init__(
        self, 
        /, 
        origin: str = "http://localhost:19798", 
        username: str = "", 
        password: str = "", 
        channel = None, 
    ):
        urlp = urlsplit(origin)
        self._origin = f"{urlp.scheme}://{urlp.netloc}"
        self.download_baseurl = f"{urlp.scheme}://{urlp.netloc}/static/{urlp.scheme}/{urlp.netloc}/False/"
        self._username = username
        self._password = password
        self.metadata: list[tuple[str, str]] = []
        if channel is None:
            channel = insecure_channel(urlp.netloc)
        self.channel = channel
        if username:
            self.login()

    def __del__(self, /):
        self.close()

    def __eq__(self, other, /) -> bool:
        return type(self) is type(other) and self.origin == other.origin

    def __hash__(self, /) -> int:
        return hash(self.origin)

    def __repr__(self, /) -> str:
        cls = type(self)
        module = cls.__module__
        name = cls.__qualname__
        if module != "__main__":
            name = module + "." + name
        return f"{name}(origin={self._origin!r}, username={self._username!r}, password='******', channel={self._channel!r})"

    def close(self, /):
        try:
            self._channel.close()
        except:
            pass

    @property
    def channel(self, /):
        return self._channel

    @channel.setter
    def channel(self, channel, /):
        if callable(channel):
            channel = channel(self.origin)
        self._channel = channel
        self._stub = CloudDrive_pb2_grpc.CloudDriveFileSrvStub(channel)

    @property
    def origin(self, /) -> str:
        return self._origin

    @property
    def username(self, /) -> str:
        return self._username

    @property
    def password(self, /) -> str:
        return self._password

    @password.setter
    def password(self, value: str, /):
        self._password = value
        self.login()

    @property
    def stub(self, /):
        return self._stub

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
        response = self._stub.GetToken(CloudDrive_pb2.GetTokenRequest(userName=username, password=password))
        self.metadata = [("authorization", "Bearer " + response.token),]

    def GetSystemInfo(self, /) -> CloudDrive_pb2.CloudDriveSystemInfo:
        """
        public methods, no authorization is required
        returns if clouddrive has logged in to cloudfs server and the user name

        ----------------------------------------------------------------

        rpc definition::

        // public methods, no authorization is required
        // returns if clouddrive has logged in to cloudfs server and the user name
        rpc GetSystemInfo(google.protobuf.Empty) returns (CloudDriveSystemInfo) {}

        ----------------------------------------------------------------

        type definition::

        message CloudDriveSystemInfo {
          bool IsLogin = 1;
          string UserName = 2;
        }
        """
        return self._stub.GetSystemInfo(Empty(), metadata=self.metadata)

    def GetToken(self, arg: CloudDrive_pb2.GetTokenRequest, /) -> CloudDrive_pb2.JWTToken:
        """
        get bearer token by username and password

        ----------------------------------------------------------------

        rpc definition::

        // get bearer token by username and password
        rpc GetToken(GetTokenRequest) returns (JWTToken) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.GetToken(arg, metadata=self.metadata)

    def Login(self, arg: CloudDrive_pb2.UserLoginRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        login to cloudfs server

        ----------------------------------------------------------------

        rpc definition::

        // login to cloudfs server
        rpc Login(UserLoginRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message UserLoginRequest {
          string userName = 1;
          string password = 2;
          bool synDataToCloud = 3;
        }
        """
        return self._stub.Login(arg, metadata=self.metadata)

    def Register(self, arg: CloudDrive_pb2.UserRegisterRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        register a new count

        ----------------------------------------------------------------

        rpc definition::

        // register a new count
        rpc Register(UserRegisterRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message UserRegisterRequest {
          string userName = 1;
          string password = 2;
        }
        """
        return self._stub.Register(arg, metadata=self.metadata)

    def SendResetAccountEmail(self, arg: CloudDrive_pb2.SendResetAccountEmailRequest, /) -> None:
        """
        asks cloudfs server to send reset account email with reset link

        ----------------------------------------------------------------

        rpc definition::

          // asks cloudfs server to send reset account email with reset link
        rpc SendResetAccountEmail(SendResetAccountEmailRequest)
            returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message SendResetAccountEmailRequest { string email = 1; }
        """
        return self._stub.SendResetAccountEmail(arg, metadata=self.metadata)

    def ResetAccount(self, arg: CloudDrive_pb2.ResetAccountRequest, /) -> None:
        """
        reset account's data, set new password, with received reset code from email

        ----------------------------------------------------------------

        rpc definition::

        // reset account's data, set new password, with received reset code from email
        rpc ResetAccount(ResetAccountRequest) returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message ResetAccountRequest {
          string resetCode = 1;
          string newPassword = 2;
        }
        """
        return self._stub.ResetAccount(arg, metadata=self.metadata)

    def SendConfirmEmail(self, /) -> None:
        """
        authorized methods, Authorization header with Bearer {token} is requirerd
        asks cloudfs server to send confirm email with confirm link

        ----------------------------------------------------------------

        rpc definition::

        // authorized methods, Authorization header with Bearer {token} is requirerd
        // asks cloudfs server to send confirm email with confirm link
        rpc SendConfirmEmail(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        return self._stub.SendConfirmEmail(Empty(), metadata=self.metadata)

    def ConfirmEmail(self, arg: CloudDrive_pb2.ConfirmEmailRequest, /) -> None:
        """
        confirm email by confirm code

        ----------------------------------------------------------------

        rpc definition::

        // confirm email by confirm code
        rpc ConfirmEmail(ConfirmEmailRequest) returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message ConfirmEmailRequest { string confirmCode = 1; }
        """
        return self._stub.ConfirmEmail(arg, metadata=self.metadata)

    def GetAccountStatus(self, /) -> CloudDrive_pb2.AccountStatusResult:
        """
        get account status

        ----------------------------------------------------------------

        rpc definition::

        // get account status
        rpc GetAccountStatus(google.protobuf.Empty) returns (AccountStatusResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.GetAccountStatus(Empty(), metadata=self.metadata)

    def GetSubFiles(self, arg: CloudDrive_pb2.ListSubFileRequest, /) -> Iterator[CloudDrive_pb2.SubFilesReply]:
        """
        get all subfiles by path

        ----------------------------------------------------------------

        rpc definition::

        // get all subfiles by path
        rpc GetSubFiles(ListSubFileRequest) returns (stream SubFilesReply) {}

        ----------------------------------------------------------------

        type definition::

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
        }
        message ListSubFileRequest {
          string path = 1;
          bool forceRefresh = 2;
        }
        message SubFilesReply { repeated CloudDriveFile subFiles = 1; }
        """
        return self._stub.GetSubFiles(arg, metadata=self.metadata)

    def GetSearchResults(self, arg: CloudDrive_pb2.SearchRequest, /) -> Iterator[CloudDrive_pb2.SubFilesReply]:
        """
        search under path

        ----------------------------------------------------------------

        rpc definition::

        // search under path
        rpc GetSearchResults(SearchRequest) returns (stream SubFilesReply) {}

        ----------------------------------------------------------------

        type definition::

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
        }
        message SearchRequest {
          string path = 1;
          string searchFor = 2;
          bool forceRefresh = 3;
          bool fuzzyMatch = 4;
        }
        message SubFilesReply { repeated CloudDriveFile subFiles = 1; }
        """
        return self._stub.GetSearchResults(arg, metadata=self.metadata)

    def FindFileByPath(self, arg: CloudDrive_pb2.FindFileByPathRequest, /) -> CloudDrive_pb2.CloudDriveFile:
        """
        find file info by full path

        ----------------------------------------------------------------

        rpc definition::

        // find file info by full path
        rpc FindFileByPath(FindFileByPathRequest) returns (CloudDriveFile) {}

        ----------------------------------------------------------------

        type definition::

        message CloudAPI {
          string name = 1;
          string userName = 2;
          string nickName = 3;
          bool isLocked = 4; //isLocked means the cloudAPI is set to can't open files, due to user's membership issue
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
        return self._stub.FindFileByPath(arg, metadata=self.metadata)

    def CreateFolder(self, arg: CloudDrive_pb2.CreateFolderRequest, /) -> CloudDrive_pb2.CreateFolderResult:
        """
        create a folder under path

        ----------------------------------------------------------------

        rpc definition::

        // create a folder under path
        rpc CreateFolder(CreateFolderRequest) returns (CreateFolderResult) {}

        ----------------------------------------------------------------

        type definition::

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
        }
        """
        return self._stub.CreateFolder(arg, metadata=self.metadata)

    def RenameFile(self, arg: CloudDrive_pb2.RenameFileRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        rename a single file

        ----------------------------------------------------------------

        rpc definition::

        // rename a single file
        rpc RenameFile(RenameFileRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message RenameFileRequest {
          string theFilePath = 1;
          string newName = 2;
        }
        """
        return self._stub.RenameFile(arg, metadata=self.metadata)

    def RenameFiles(self, arg: CloudDrive_pb2.RenameFilesRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        batch rename files

        ----------------------------------------------------------------

        rpc definition::

        // batch rename files
        rpc RenameFiles(RenameFilesRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message RenameFileRequest {
          string theFilePath = 1;
          string newName = 2;
        }
        message RenameFilesRequest { repeated RenameFileRequest renameFiles = 1; }
        """
        return self._stub.RenameFiles(arg, metadata=self.metadata)

    def MoveFile(self, arg: CloudDrive_pb2.MoveFileRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        move files to a dest folder

        ----------------------------------------------------------------

        rpc definition::

        // move files to a dest folder
        rpc MoveFile(MoveFileRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message MoveFileRequest {
          repeated string theFilePaths = 1;
          string destPath = 2;
        }
        """
        return self._stub.MoveFile(arg, metadata=self.metadata)

    def DeleteFile(self, arg: CloudDrive_pb2.FileRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        delete a single file

        ----------------------------------------------------------------

        rpc definition::

        // delete a single file
        rpc DeleteFile(FileRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message FileRequest { string path = 1; }
        """
        return self._stub.DeleteFile(arg, metadata=self.metadata)

    def DeleteFilePermanently(self, arg: CloudDrive_pb2.FileRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        delete a single file permanently, only aliyundrive supports this currently

        ----------------------------------------------------------------

        rpc definition::

        // delete a single file permanently, only aliyundrive supports this currently
        rpc DeleteFilePermanently(FileRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message FileRequest { string path = 1; }
        """
        return self._stub.DeleteFilePermanently(arg, metadata=self.metadata)

    def DeleteFiles(self, arg: CloudDrive_pb2.MultiFileRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        batch delete files

        ----------------------------------------------------------------

        rpc definition::

        // batch delete files
        rpc DeleteFiles(MultiFileRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message MultiFileRequest { repeated string path = 1; }
        """
        return self._stub.DeleteFiles(arg, metadata=self.metadata)

    def DeleteFilesPermanently(self, arg: CloudDrive_pb2.MultiFileRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        batch delete files permanently, only aliyundrive supports this currently

        ----------------------------------------------------------------

        rpc definition::

        // batch delete files permanently, only aliyundrive supports this currently
        rpc DeleteFilesPermanently(MultiFileRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message MultiFileRequest { repeated string path = 1; }
        """
        return self._stub.DeleteFilesPermanently(arg, metadata=self.metadata)

    def AddOfflineFiles(self, arg: CloudDrive_pb2.AddOfflineFileRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        add offline files by providing magnet, sha1, ..., applies only with folders
        with canOfflineDownload is tru

        ----------------------------------------------------------------

        rpc definition::

        // add offline files by providing magnet, sha1, ..., applies only with folders
        // with canOfflineDownload is tru
        rpc AddOfflineFiles(AddOfflineFileRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message AddOfflineFileRequest {
          string urls = 1;
          string toFolder = 2;
        }
        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        """
        return self._stub.AddOfflineFiles(arg, metadata=self.metadata)

    def ListOfflineFilesByPath(self, arg: CloudDrive_pb2.FileRequest, /) -> CloudDrive_pb2.OfflineFileListResult:
        """
        list offline files

        ----------------------------------------------------------------

        rpc definition::

        // list offline files
        rpc ListOfflineFilesByPath(FileRequest) returns (OfflineFileListResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.ListOfflineFilesByPath(arg, metadata=self.metadata)

    def ListAllOfflineFiles(self, arg: CloudDrive_pb2.OfflineFileListAllRequest, /) -> CloudDrive_pb2.OfflineFileListAllResult:
        """
        list all offline files of a cloud with pagination

        ----------------------------------------------------------------

        rpc definition::

        // list all offline files of a cloud with pagination
        rpc ListAllOfflineFiles(OfflineFileListAllRequest)
            returns (OfflineFileListAllResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.ListAllOfflineFiles(arg, metadata=self.metadata)

    def AddSharedLink(self, arg: CloudDrive_pb2.AddSharedLinkRequest, /) -> None:
        """
        add a shared link to a folder, with shared_link_url, shared_password

        ----------------------------------------------------------------

        rpc definition::

        // add a shared link to a folder, with shared_link_url, shared_password
        rpc AddSharedLink(AddSharedLinkRequest) returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message AddSharedLinkRequest {
          string sharedLinkUrl = 1;
          string sharedPassword = 2;
          string toFolder = 3;
        }
        """
        return self._stub.AddSharedLink(arg, metadata=self.metadata)

    def GetFileDetailProperties(self, arg: CloudDrive_pb2.FileRequest, /) -> CloudDrive_pb2.FileDetailProperties:
        """
        get folder properties, applies only with folders with hasDetailProperties
        is true

        ----------------------------------------------------------------

        rpc definition::

        // get folder properties, applies only with folders with hasDetailProperties
        // is true
        rpc GetFileDetailProperties(FileRequest) returns (FileDetailProperties) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.GetFileDetailProperties(arg, metadata=self.metadata)

    def GetSpaceInfo(self, arg: CloudDrive_pb2.FileRequest, /) -> CloudDrive_pb2.SpaceInfo:
        """
        get total/free/used space of a cloud path

        ----------------------------------------------------------------

        rpc definition::

        // get total/free/used space of a cloud path
        rpc GetSpaceInfo(FileRequest) returns (SpaceInfo) {}

        ----------------------------------------------------------------

        type definition::

        message FileRequest { string path = 1; }
        message SpaceInfo {
          int64 totalSpace = 1;
          int64 usedSpace = 2;
          int64 freeSpace = 3;
        }
        """
        return self._stub.GetSpaceInfo(arg, metadata=self.metadata)

    def GetCloudMemberships(self, arg: CloudDrive_pb2.FileRequest, /) -> CloudDrive_pb2.CloudMemberships:
        """
        get cloud account memberships

        ----------------------------------------------------------------

        rpc definition::

        // get cloud account memberships
        rpc GetCloudMemberships(FileRequest) returns (CloudMemberships) {}

        ----------------------------------------------------------------

        type definition::

        message CloudMembership {
          string identity = 1;
          optional google.protobuf.Timestamp expireTime = 2;
          optional string level = 3;
        }
        message CloudMemberships { repeated CloudMembership memberships = 1; }
        message FileRequest { string path = 1; }
        """
        return self._stub.GetCloudMemberships(arg, metadata=self.metadata)

    def GetRuntimeInfo(self, /) -> CloudDrive_pb2.RuntimeInfo:
        """
        get server runtime info

        ----------------------------------------------------------------

        rpc definition::

        // get server runtime info
        rpc GetRuntimeInfo(google.protobuf.Empty) returns (RuntimeInfo) {}

        ----------------------------------------------------------------

        type definition::

        message RuntimeInfo {
          string productName = 1;
          string productVersion = 2;
          string CloudAPIVersion = 3;
          string osInfo = 4;
        }
        """
        return self._stub.GetRuntimeInfo(Empty(), metadata=self.metadata)

    def GetRunningInfo(self, /) -> CloudDrive_pb2.RunInfo:
        """
        get server stats, including cpu/mem/uptime

        ----------------------------------------------------------------

        rpc definition::

        // get server stats, including cpu/mem/uptime
        rpc GetRunningInfo(google.protobuf.Empty) returns (RunInfo) {}

        ----------------------------------------------------------------

        type definition::

        message RunInfo {
          double cpuUsage = 1;
          uint64 memUsageKB = 2;
          double uptime = 3;
          uint64 fhTableCount = 4;
          uint64 dirCacheCount = 5;
          uint64 tempFileCount = 6;
        }
        """
        return self._stub.GetRunningInfo(Empty(), metadata=self.metadata)

    def Logout(self, arg: CloudDrive_pb2.UserLogoutRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        logout from cloudfs server

        ----------------------------------------------------------------

        rpc definition::

        // logout from cloudfs server
        rpc Logout(UserLogoutRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message UserLogoutRequest { bool logoutFromCloudFS = 1; }
        """
        return self._stub.Logout(arg, metadata=self.metadata)

    def CanAddMoreMountPoints(self, /) -> CloudDrive_pb2.FileOperationResult:
        """
        check if current user can add more mount point

        ----------------------------------------------------------------

        rpc definition::

        // check if current user can add more mount point
        rpc CanAddMoreMountPoints(google.protobuf.Empty)
            returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        """
        return self._stub.CanAddMoreMountPoints(Empty(), metadata=self.metadata)

    def GetMountPoints(self, /) -> CloudDrive_pb2.GetMountPointsResult:
        """
        get all mount points

        ----------------------------------------------------------------

        rpc definition::

        // get all mount points
        rpc GetMountPoints(google.protobuf.Empty) returns (GetMountPointsResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.GetMountPoints(Empty(), metadata=self.metadata)

    def AddMountPoint(self, arg: CloudDrive_pb2.MountOption, /) -> CloudDrive_pb2.MountPointResult:
        """
        add a new mount point

        ----------------------------------------------------------------

        rpc definition::

        // add a new mount point
        rpc AddMountPoint(MountOption) returns (MountPointResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.AddMountPoint(arg, metadata=self.metadata)

    def RemoveMountPoint(self, arg: CloudDrive_pb2.MountPointRequest, /) -> CloudDrive_pb2.MountPointResult:
        """
        remove a mountpoint

        ----------------------------------------------------------------

        rpc definition::

        // remove a mountpoint
        rpc RemoveMountPoint(MountPointRequest) returns (MountPointResult) {}

        ----------------------------------------------------------------

        type definition::

        message MountPointRequest { string MountPoint = 1; }
        message MountPointResult {
          bool success = 1;
          string failReason = 2;
        }
        """
        return self._stub.RemoveMountPoint(arg, metadata=self.metadata)

    def Mount(self, arg: CloudDrive_pb2.MountPointRequest, /) -> CloudDrive_pb2.MountPointResult:
        """
        mount a mount point

        ----------------------------------------------------------------

        rpc definition::

        // mount a mount point
        rpc Mount(MountPointRequest) returns (MountPointResult) {}

        ----------------------------------------------------------------

        type definition::

        message MountPointRequest { string MountPoint = 1; }
        message MountPointResult {
          bool success = 1;
          string failReason = 2;
        }
        """
        return self._stub.Mount(arg, metadata=self.metadata)

    def Unmount(self, arg: CloudDrive_pb2.MountPointRequest, /) -> CloudDrive_pb2.MountPointResult:
        """
        unmount a mount point

        ----------------------------------------------------------------

        rpc definition::

        // unmount a mount point
        rpc Unmount(MountPointRequest) returns (MountPointResult) {}

        ----------------------------------------------------------------

        type definition::

        message MountPointRequest { string MountPoint = 1; }
        message MountPointResult {
          bool success = 1;
          string failReason = 2;
        }
        """
        return self._stub.Unmount(arg, metadata=self.metadata)

    def UpdateMountPoint(self, arg: CloudDrive_pb2.UpdateMountPointRequest, /) -> CloudDrive_pb2.MountPointResult:
        """
        change mount point settings

        ----------------------------------------------------------------

        rpc definition::

        // change mount point settings
        rpc UpdateMountPoint(UpdateMountPointRequest) returns (MountPointResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.UpdateMountPoint(arg, metadata=self.metadata)

    def GetAvailableDriveLetters(self, /) -> CloudDrive_pb2.GetAvailableDriveLettersResult:
        """
        get all unused drive letters from server's local storage, applies to
        windows only

        ----------------------------------------------------------------

        rpc definition::

        // get all unused drive letters from server's local storage, applies to
        // windows only
        rpc GetAvailableDriveLetters(google.protobuf.Empty)
            returns (GetAvailableDriveLettersResult) {}

        ----------------------------------------------------------------

        type definition::

        message GetAvailableDriveLettersResult { repeated string driveLetters = 1; }
        """
        return self._stub.GetAvailableDriveLetters(Empty(), metadata=self.metadata)

    def HasDriveLetters(self, /) -> CloudDrive_pb2.HasDriveLettersResult:
        """
        check if server has driver letters, returns true only on windows

        ----------------------------------------------------------------

        rpc definition::

        // check if server has driver letters, returns true only on windows
        rpc HasDriveLetters(google.protobuf.Empty) returns (HasDriveLettersResult) {}

        ----------------------------------------------------------------

        type definition::

        message HasDriveLettersResult { bool hasDriveLetters = 1; }
        """
        return self._stub.HasDriveLetters(Empty(), metadata=self.metadata)

    def LocalGetSubFiles(self, arg: CloudDrive_pb2.LocalGetSubFilesRequest, /) -> Iterator[CloudDrive_pb2.LocalGetSubFilesResult]:
        """
        get subfiles of a local path, used for adding mountpoint from web ui

        ----------------------------------------------------------------

        rpc definition::

        // get subfiles of a local path, used for adding mountpoint from web ui
        rpc LocalGetSubFiles(LocalGetSubFilesRequest)
            returns (stream LocalGetSubFilesResult) {}

        ----------------------------------------------------------------

        type definition::

        message LocalGetSubFilesRequest {
          string parentFolder = 1;
          bool folderOnly = 2;
          bool includeCloudDrive = 3;
          bool includeAvailableDrive = 4;
        }
        message LocalGetSubFilesResult { repeated string subFiles = 1; }
        """
        return self._stub.LocalGetSubFiles(arg, metadata=self.metadata)

    def GetAllTasksCount(self, /) -> CloudDrive_pb2.GetAllTasksCountResult:
        """
        get all transfer tasks' count

        ----------------------------------------------------------------

        rpc definition::

        // get all transfer tasks' count
        rpc GetAllTasksCount(google.protobuf.Empty) returns (GetAllTasksCountResult) {
        }

        ----------------------------------------------------------------

        type definition::

        message GetAllTasksCountResult {
          uint32 downloadCount = 1;
          uint32 uploadCount = 2;
          PushMessage pushMessage = 3;
          bool hasUpdate = 4;
        }
        message PushMessage { string clouddriveVersion = 1; }
        """
        return self._stub.GetAllTasksCount(Empty(), metadata=self.metadata)

    def GetDownloadFileCount(self, /) -> CloudDrive_pb2.GetDownloadFileCountResult:
        """
        get download tasks' count

        ----------------------------------------------------------------

        rpc definition::

        // get download tasks' count
        rpc GetDownloadFileCount(google.protobuf.Empty)
            returns (GetDownloadFileCountResult) {}

        ----------------------------------------------------------------

        type definition::

        message GetDownloadFileCountResult { uint32 fileCount = 1; }
        """
        return self._stub.GetDownloadFileCount(Empty(), metadata=self.metadata)

    def GetDownloadFileList(self, /) -> CloudDrive_pb2.GetDownloadFileListResult:
        """
        get all download tasks

        ----------------------------------------------------------------

        rpc definition::

        // get all download tasks
        rpc GetDownloadFileList(google.protobuf.Empty)
            returns (GetDownloadFileListResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.GetDownloadFileList(Empty(), metadata=self.metadata)

    def GetUploadFileCount(self, /) -> CloudDrive_pb2.GetUploadFileCountResult:
        """
        get all upload tasks' count

        ----------------------------------------------------------------

        rpc definition::

        // get all upload tasks' count
        rpc GetUploadFileCount(google.protobuf.Empty)
            returns (GetUploadFileCountResult) {}

        ----------------------------------------------------------------

        type definition::

        message GetUploadFileCountResult { uint32 fileCount = 1; }
        """
        return self._stub.GetUploadFileCount(Empty(), metadata=self.metadata)

    def GetUploadFileList(self, arg: CloudDrive_pb2.GetUploadFileListRequest, /) -> CloudDrive_pb2.GetUploadFileListResult:
        """
        get upload tasks, paged by providing page number and items per page and
        file name filter

        ----------------------------------------------------------------

        rpc definition::

        // get upload tasks, paged by providing page number and items per page and
        // file name filter
        rpc GetUploadFileList(GetUploadFileListRequest)
            returns (GetUploadFileListResult) {}

        ----------------------------------------------------------------

        type definition::

        message GetUploadFileListRequest {
          bool getAll = 1;
          uint32 itemsPerPage = 2;
          uint32 pageNumber = 3;
          string filter = 4;
        }
        message GetUploadFileListResult {
          uint32 totalCount = 1;
          repeated UploadFileInfo uploadFiles = 2;
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
        return self._stub.GetUploadFileList(arg, metadata=self.metadata)

    def CancelAllUploadFiles(self, /) -> None:
        """
        cancel all upload tasks

        ----------------------------------------------------------------

        rpc definition::

        // cancel all upload tasks
        rpc CancelAllUploadFiles(google.protobuf.Empty)
            returns (google.protobuf.Empty) {}
        """
        return self._stub.CancelAllUploadFiles(Empty(), metadata=self.metadata)

    def CancelUploadFiles(self, arg: CloudDrive_pb2.MultpleUploadFileKeyRequest, /) -> None:
        """
        cancel selected upload tasks

        ----------------------------------------------------------------

        rpc definition::

        // cancel selected upload tasks
        rpc CancelUploadFiles(MultpleUploadFileKeyRequest)
            returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message MultpleUploadFileKeyRequest { repeated string keys = 1; }
        """
        return self._stub.CancelUploadFiles(arg, metadata=self.metadata)

    def PauseAllUploadFiles(self, /) -> None:
        """
        pause all upload tasks

        ----------------------------------------------------------------

        rpc definition::

        // pause all upload tasks
        rpc PauseAllUploadFiles(google.protobuf.Empty)
            returns (google.protobuf.Empty) {}
        """
        return self._stub.PauseAllUploadFiles(Empty(), metadata=self.metadata)

    def PauseUploadFiles(self, arg: CloudDrive_pb2.MultpleUploadFileKeyRequest, /) -> None:
        """
        pause selected upload tasks

        ----------------------------------------------------------------

        rpc definition::

        // pause selected upload tasks
        rpc PauseUploadFiles(MultpleUploadFileKeyRequest)
            returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message MultpleUploadFileKeyRequest { repeated string keys = 1; }
        """
        return self._stub.PauseUploadFiles(arg, metadata=self.metadata)

    def ResumeAllUploadFiles(self, /) -> None:
        """
        resume all upload tasks

        ----------------------------------------------------------------

        rpc definition::

        // resume all upload tasks
        rpc ResumeAllUploadFiles(google.protobuf.Empty)
            returns (google.protobuf.Empty) {}
        """
        return self._stub.ResumeAllUploadFiles(Empty(), metadata=self.metadata)

    def ResumeUploadFiles(self, arg: CloudDrive_pb2.MultpleUploadFileKeyRequest, /) -> None:
        """
        resume selected upload tasks

        ----------------------------------------------------------------

        rpc definition::

        // resume selected upload tasks
        rpc ResumeUploadFiles(MultpleUploadFileKeyRequest)
            returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message MultpleUploadFileKeyRequest { repeated string keys = 1; }
        """
        return self._stub.ResumeUploadFiles(arg, metadata=self.metadata)

    def CanAddMoreCloudApis(self, /) -> CloudDrive_pb2.FileOperationResult:
        """
        check if current user can add more cloud apis

        ----------------------------------------------------------------

        rpc definition::

        // check if current user can add more cloud apis
        rpc CanAddMoreCloudApis(google.protobuf.Empty)
            returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        """
        return self._stub.CanAddMoreCloudApis(Empty(), metadata=self.metadata)

    def APILogin115Editthiscookie(self, arg: CloudDrive_pb2.Login115EditthiscookieRequest, /) -> CloudDrive_pb2.APILoginResult:
        """
        add 115 cloud with editthiscookie

        ----------------------------------------------------------------

        rpc definition::

        // add 115 cloud with editthiscookie
        rpc APILogin115Editthiscookie(Login115EditthiscookieRequest)
            returns (APILoginResult) {}

        ----------------------------------------------------------------

        type definition::

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message Login115EditthiscookieRequest { string editThiscookieString = 1; }
        """
        return self._stub.APILogin115Editthiscookie(arg, metadata=self.metadata)

    def APILogin115QRCode(self, arg: CloudDrive_pb2.Login115QrCodeRequest, /) -> Iterator[CloudDrive_pb2.QRCodeScanMessage]:
        """
        add 115 cloud with qr scanning

        ----------------------------------------------------------------

        rpc definition::

        // add 115 cloud with qr scanning
        rpc APILogin115QRCode(Login115QrCodeRequest)
            returns (stream QRCodeScanMessage) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.APILogin115QRCode(arg, metadata=self.metadata)

    def APILoginAliyundriveOAuth(self, arg: CloudDrive_pb2.LoginAliyundriveOAuthRequest, /) -> CloudDrive_pb2.APILoginResult:
        """
        add AliyunDriveOpen with OAuth result

        ----------------------------------------------------------------

        rpc definition::

        // add AliyunDriveOpen with OAuth result
        rpc APILoginAliyundriveOAuth(LoginAliyundriveOAuthRequest)
            returns (APILoginResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.APILoginAliyundriveOAuth(arg, metadata=self.metadata)

    def APILoginAliyundriveRefreshtoken(self, arg: CloudDrive_pb2.LoginAliyundriveRefreshtokenRequest, /) -> CloudDrive_pb2.APILoginResult:
        """
        add AliyunDrive with refresh token

        ----------------------------------------------------------------

        rpc definition::

        // add AliyunDrive with refresh token
        rpc APILoginAliyundriveRefreshtoken(LoginAliyundriveRefreshtokenRequest)
            returns (APILoginResult) {}

        ----------------------------------------------------------------

        type definition::

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message LoginAliyundriveRefreshtokenRequest {
          string refreshToken = 1;
          bool useOpenAPI = 2;
        }
        """
        return self._stub.APILoginAliyundriveRefreshtoken(arg, metadata=self.metadata)

    def APILoginAliyunDriveQRCode(self, arg: CloudDrive_pb2.LoginAliyundriveQRCodeRequest, /) -> Iterator[CloudDrive_pb2.QRCodeScanMessage]:
        """
        add AliyunDrive with qr scanning

        ----------------------------------------------------------------

        rpc definition::

        // add AliyunDrive with qr scanning
        rpc APILoginAliyunDriveQRCode(LoginAliyundriveQRCodeRequest)
            returns (stream QRCodeScanMessage) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.APILoginAliyunDriveQRCode(arg, metadata=self.metadata)

    def APILoginBaiduPanOAuth(self, arg: CloudDrive_pb2.LoginBaiduPanOAuthRequest, /) -> CloudDrive_pb2.APILoginResult:
        """
        add BaiduPan with OAuth result

        ----------------------------------------------------------------

        rpc definition::

        // add BaiduPan with OAuth result
        rpc APILoginBaiduPanOAuth(LoginBaiduPanOAuthRequest)
            returns (APILoginResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.APILoginBaiduPanOAuth(arg, metadata=self.metadata)

    def APILoginOneDriveOAuth(self, arg: CloudDrive_pb2.LoginOneDriveOAuthRequest, /) -> CloudDrive_pb2.APILoginResult:
        """
        add OneDrive with OAuth result

        ----------------------------------------------------------------

        rpc definition::

        // add OneDrive with OAuth result
        rpc APILoginOneDriveOAuth(LoginOneDriveOAuthRequest)
          returns (APILoginResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.APILoginOneDriveOAuth(arg, metadata=self.metadata)

    def ApiLoginGoogleDriveOAuth(self, arg: CloudDrive_pb2.LoginGoogleDriveOAuthRequest, /) -> CloudDrive_pb2.APILoginResult:
        """
        add Google Drive with OAuth result

        ----------------------------------------------------------------

        rpc definition::

        // add Google Drive with OAuth result
        rpc ApiLoginGoogleDriveOAuth(LoginGoogleDriveOAuthRequest)
            returns (APILoginResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.ApiLoginGoogleDriveOAuth(arg, metadata=self.metadata)

    def ApiLoginGoogleDriveRefreshToken(self, arg: CloudDrive_pb2.LoginGoogleDriveRefreshTokenRequest, /) -> CloudDrive_pb2.APILoginResult:
        """
        add Google Drive with refresh token

        ----------------------------------------------------------------

        rpc definition::

        // add Google Drive with refresh token
        rpc ApiLoginGoogleDriveRefreshToken(LoginGoogleDriveRefreshTokenRequest)
            returns (APILoginResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.ApiLoginGoogleDriveRefreshToken(arg, metadata=self.metadata)

    def APILogin189QRCode(self, /) -> Iterator[CloudDrive_pb2.QRCodeScanMessage]:
        """
        add 189 cloud with qr scanning

        ----------------------------------------------------------------

        rpc definition::

        // add 189 cloud with qr scanning
        rpc APILogin189QRCode(google.protobuf.Empty)
            returns (stream QRCodeScanMessage) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.APILogin189QRCode(Empty(), metadata=self.metadata)

    def APILoginPikPak(self, arg: CloudDrive_pb2.UserLoginRequest, /) -> CloudDrive_pb2.APILoginResult:
        """
        add PikPak cloud with username and password

        ----------------------------------------------------------------

        rpc definition::

        // add PikPak cloud with username and password
        rpc APILoginPikPak(UserLoginRequest) returns (APILoginResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.APILoginPikPak(arg, metadata=self.metadata)

    def APILoginWebDav(self, arg: CloudDrive_pb2.LoginWebDavRequest, /) -> CloudDrive_pb2.APILoginResult:
        """
        add webdav

        ----------------------------------------------------------------

        rpc definition::

        // add webdav
        rpc APILoginWebDav(LoginWebDavRequest) returns (APILoginResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.APILoginWebDav(arg, metadata=self.metadata)

    def APIAddLocalFolder(self, arg: CloudDrive_pb2.AddLocalFolderRequest, /) -> CloudDrive_pb2.APILoginResult:
        """
        add local folder

        ----------------------------------------------------------------

        rpc definition::

        // add local folder
        rpc APIAddLocalFolder(AddLocalFolderRequest) returns (APILoginResult) {}

        ----------------------------------------------------------------

        type definition::

        message APILoginResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message AddLocalFolderRequest { string localFolderPath = 1; }
        """
        return self._stub.APIAddLocalFolder(arg, metadata=self.metadata)

    def RemoveCloudAPI(self, arg: CloudDrive_pb2.RemoveCloudAPIRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        remove a cloud

        ----------------------------------------------------------------

        rpc definition::

        // remove a cloud
        rpc RemoveCloudAPI(RemoveCloudAPIRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        message RemoveCloudAPIRequest {
          string cloudName = 1;
          string userName = 2;
          bool permanentRemove = 3;
        }
        """
        return self._stub.RemoveCloudAPI(arg, metadata=self.metadata)

    def GetAllCloudApis(self, /) -> CloudDrive_pb2.CloudAPIList:
        """
        get all cloud apis

        ----------------------------------------------------------------

        rpc definition::

        // get all cloud apis
        rpc GetAllCloudApis(google.protobuf.Empty) returns (CloudAPIList) {}

        ----------------------------------------------------------------

        type definition::

        message CloudAPI {
          string name = 1;
          string userName = 2;
          string nickName = 3;
          bool isLocked = 4; //isLocked means the cloudAPI is set to can't open files, due to user's membership issue
        }
        message CloudAPIList {
          repeated CloudAPI apis = 1;
        }
        """
        return self._stub.GetAllCloudApis(Empty(), metadata=self.metadata)

    def GetCloudAPIConfig(self, arg: CloudDrive_pb2.GetCloudAPIConfigRequest, /) -> CloudDrive_pb2.CloudAPIConfig:
        """
        get CloudAPI configuration

        ----------------------------------------------------------------

        rpc definition::

        // get CloudAPI configuration
        rpc GetCloudAPIConfig(GetCloudAPIConfigRequest) returns (CloudAPIConfig) {}

        ----------------------------------------------------------------

        type definition::

        message CloudAPIConfig {
          uint32 maxDownloadThreads = 1;
          uint64 minReadLengthKB = 2;
          uint64 maxReadLengthKB = 3;
          uint64 defaultReadLengthKB = 4;
          uint64 maxBufferPoolSizeMB = 5;
          double maxQueriesPerSecond = 6;
          bool forceIpv4 = 7;
        }
        message GetCloudAPIConfigRequest {
          string cloudName = 1;
          string userName = 2;
        }
        """
        return self._stub.GetCloudAPIConfig(arg, metadata=self.metadata)

    def SetCloudAPIConfig(self, arg: CloudDrive_pb2.SetCloudAPIConfigRequest, /) -> None:
        """
        set CloudAPI configuration

        ----------------------------------------------------------------

        rpc definition::

        // set CloudAPI configuration
        rpc SetCloudAPIConfig(SetCloudAPIConfigRequest)
            returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message CloudAPIConfig {
          uint32 maxDownloadThreads = 1;
          uint64 minReadLengthKB = 2;
          uint64 maxReadLengthKB = 3;
          uint64 defaultReadLengthKB = 4;
          uint64 maxBufferPoolSizeMB = 5;
          double maxQueriesPerSecond = 6;
          bool forceIpv4 = 7;
        }
        message SetCloudAPIConfigRequest {
          string cloudName = 1;
          string userName = 2;
          CloudAPIConfig config = 3;
        }
        """
        return self._stub.SetCloudAPIConfig(arg, metadata=self.metadata)

    def GetSystemSettings(self, /) -> CloudDrive_pb2.SystemSettings:
        """
        get all system setings value

        ----------------------------------------------------------------

        rpc definition::

        // get all system setings value
        rpc GetSystemSettings(google.protobuf.Empty) returns (SystemSettings) {}

        ----------------------------------------------------------------

        type definition::

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
        }
        """
        return self._stub.GetSystemSettings(Empty(), metadata=self.metadata)

    def SetSystemSettings(self, arg: CloudDrive_pb2.SystemSettings, /) -> None:
        """
        set selected system settings value

        ----------------------------------------------------------------

        rpc definition::

        // set selected system settings value
        rpc SetSystemSettings(SystemSettings) returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

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
        }
        """
        return self._stub.SetSystemSettings(arg, metadata=self.metadata)

    def SetDirCacheTimeSecs(self, arg: CloudDrive_pb2.SetDirCacheTimeRequest, /) -> None:
        """
        set dir cache time

        ----------------------------------------------------------------

        rpc definition::

        // set dir cache time
        rpc SetDirCacheTimeSecs(SetDirCacheTimeRequest)
            returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message SetDirCacheTimeRequest {
          string path = 1;
          // if not present, please delete the value to restore default
          optional uint64 dirCachTimeToLiveSecs = 2;
        }
        """
        return self._stub.SetDirCacheTimeSecs(arg, metadata=self.metadata)

    def GetEffectiveDirCacheTimeSecs(self, arg: CloudDrive_pb2.GetEffectiveDirCacheTimeRequest, /) -> CloudDrive_pb2.GetEffectiveDirCacheTimeResult:
        """
        get dir cache time in effect (default value will be returned)

        ----------------------------------------------------------------

        rpc definition::

        // get dir cache time in effect (default value will be returned)
        rpc GetEffectiveDirCacheTimeSecs(GetEffectiveDirCacheTimeRequest)
            returns (GetEffectiveDirCacheTimeResult) {}

        ----------------------------------------------------------------

        type definition::

        message GetEffectiveDirCacheTimeRequest { string path = 1; }
        message GetEffectiveDirCacheTimeResult { uint64 dirCacheTimeSecs = 1; }
        """
        return self._stub.GetEffectiveDirCacheTimeSecs(arg, metadata=self.metadata)

    def GetOpenFileTable(self, arg: CloudDrive_pb2.GetOpenFileTableRequest, /) -> CloudDrive_pb2.OpenFileTable:
        """
        get open file table

        ----------------------------------------------------------------

        rpc definition::

        // get open file table
        rpc GetOpenFileTable(GetOpenFileTableRequest) returns (OpenFileTable) {}

        ----------------------------------------------------------------

        type definition::

        message GetOpenFileTableRequest { bool includeDir = 1; }
        message OpenFileTable {
          map<uint64, string> openFileTable = 1;
          uint64 localOpenFileCount = 2;
        }
        """
        return self._stub.GetOpenFileTable(arg, metadata=self.metadata)

    def GetDirCacheTable(self, /) -> CloudDrive_pb2.DirCacheTable:
        """
        get dir cache table

        ----------------------------------------------------------------

        rpc definition::

        // get dir cache table
        rpc GetDirCacheTable(google.protobuf.Empty) returns (DirCacheTable) {}

        ----------------------------------------------------------------

        type definition::

        message DirCacheTable { map<string, DirCacheItem> dirCacheTable = 1; }
        """
        return self._stub.GetDirCacheTable(Empty(), metadata=self.metadata)

    def GetReferencedEntryPaths(self, arg: CloudDrive_pb2.FileRequest, /) -> CloudDrive_pb2.StringList:
        """
        get referenced entry paths of parent path

        ----------------------------------------------------------------

        rpc definition::

        // get referenced entry paths of parent path
        rpc GetReferencedEntryPaths(FileRequest) returns (StringList) {}

        ----------------------------------------------------------------

        type definition::

        message FileRequest { string path = 1; }
        message StringList { repeated string values = 1; }
        """
        return self._stub.GetReferencedEntryPaths(arg, metadata=self.metadata)

    def GetTempFileTable(self, /) -> CloudDrive_pb2.TempFileTable:
        """
        get temp file table

        ----------------------------------------------------------------

        rpc definition::

        // get temp file table
        rpc GetTempFileTable(google.protobuf.Empty) returns (TempFileTable) {}

        ----------------------------------------------------------------

        type definition::

        message TempFileTable {
          uint64 count = 1;
          repeated string tempFiles = 2;
        }
        """
        return self._stub.GetTempFileTable(Empty(), metadata=self.metadata)

    def PushTaskChange(self, /) -> Iterator[CloudDrive_pb2.GetAllTasksCountResult]:
        """
        push upload/download task count changes to client, also can be used for
        client to detect conenction broken

        ----------------------------------------------------------------

        rpc definition::

        // push upload/download task count changes to client, also can be used for
        // client to detect conenction broken
        rpc PushTaskChange(google.protobuf.Empty)
            returns (stream GetAllTasksCountResult) {}

        ----------------------------------------------------------------

        type definition::

        message GetAllTasksCountResult {
          uint32 downloadCount = 1;
          uint32 uploadCount = 2;
          PushMessage pushMessage = 3;
          bool hasUpdate = 4;
        }
        message PushMessage { string clouddriveVersion = 1; }
        """
        return self._stub.PushTaskChange(Empty(), metadata=self.metadata)

    def GetCloudDrive1UserData(self, /) -> CloudDrive_pb2.StringResult:
        """
        get CloudDrive1's user data string

        ----------------------------------------------------------------

        rpc definition::

        // get CloudDrive1's user data string
        rpc GetCloudDrive1UserData(google.protobuf.Empty) returns (StringResult) {}

        ----------------------------------------------------------------

        type definition::

        message StringResult { string result = 1; }
        """
        return self._stub.GetCloudDrive1UserData(Empty(), metadata=self.metadata)

    def RestartService(self, /) -> None:
        """
        restart service

        ----------------------------------------------------------------

        rpc definition::

        // restart service
        rpc RestartService(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        return self._stub.RestartService(Empty(), metadata=self.metadata)

    def ShutdownService(self, /) -> None:
        """
        shutdown service

        ----------------------------------------------------------------

        rpc definition::

        // shutdown service
        rpc ShutdownService(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        return self._stub.ShutdownService(Empty(), metadata=self.metadata)

    def HasUpdate(self, /) -> CloudDrive_pb2.UpdateResult:
        """
        check if has updates available

        ----------------------------------------------------------------

        rpc definition::

        // check if has updates available
        rpc HasUpdate(google.protobuf.Empty) returns (UpdateResult) {}

        ----------------------------------------------------------------

        type definition::

        message UpdateResult {
          bool hasUpdate = 1;
          string newVersion = 2;
          string description = 3;
        }
        """
        return self._stub.HasUpdate(Empty(), metadata=self.metadata)

    def CheckUpdate(self, /) -> CloudDrive_pb2.UpdateResult:
        """
        check software updates

        ----------------------------------------------------------------

        rpc definition::

        // check software updates
        rpc CheckUpdate(google.protobuf.Empty) returns (UpdateResult) {}

        ----------------------------------------------------------------

        type definition::

        message UpdateResult {
          bool hasUpdate = 1;
          string newVersion = 2;
          string description = 3;
        }
        """
        return self._stub.CheckUpdate(Empty(), metadata=self.metadata)

    def DownloadUpdate(self, /) -> None:
        """
        download newest version

        ----------------------------------------------------------------

        rpc definition::

        // download newest version
        rpc DownloadUpdate(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        return self._stub.DownloadUpdate(Empty(), metadata=self.metadata)

    def UpdateSystem(self, /) -> None:
        """
        update to newest version

        ----------------------------------------------------------------

        rpc definition::

        // update to newest version
        rpc UpdateSystem(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        return self._stub.UpdateSystem(Empty(), metadata=self.metadata)

    def GetMetaData(self, arg: CloudDrive_pb2.FileRequest, /) -> CloudDrive_pb2.FileMetaData:
        """
        get file metadata

        ----------------------------------------------------------------

        rpc definition::

        // get file metadata
        rpc GetMetaData(FileRequest) returns (FileMetaData) {}

        ----------------------------------------------------------------

        type definition::

        message FileMetaData { map<string, string> metadata = 1; }
        message FileRequest { string path = 1; }
        """
        return self._stub.GetMetaData(arg, metadata=self.metadata)

    def GetOriginalPath(self, arg: CloudDrive_pb2.FileRequest, /) -> CloudDrive_pb2.StringResult:
        """
        get file's original path from search result

        ----------------------------------------------------------------

        rpc definition::

        // get file's original path from search result
        rpc GetOriginalPath(FileRequest) returns (StringResult) {}

        ----------------------------------------------------------------

        type definition::

        message FileRequest { string path = 1; }
        message StringResult { string result = 1; }
        """
        return self._stub.GetOriginalPath(arg, metadata=self.metadata)

    def ChangePassword(self, arg: CloudDrive_pb2.ChangePasswordRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        change password

        ----------------------------------------------------------------

        rpc definition::

        // change password
        rpc ChangePassword(ChangePasswordRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message ChangePasswordRequest {
          string oldPassword = 1;
          string newPassword = 2;
        }
        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        """
        return self._stub.ChangePassword(arg, metadata=self.metadata)

    def CreateFile(self, arg: CloudDrive_pb2.CreateFileRequest, /) -> CloudDrive_pb2.CreateFileResult:
        """
        create a new file

        ----------------------------------------------------------------

        rpc definition::

        // create a new file
        rpc CreateFile(CreateFileRequest) returns (CreateFileResult) {}

        ----------------------------------------------------------------

        type definition::

        message CreateFileRequest {
          string parentPath = 1;
          string fileName = 2;
        }
        message CreateFileResult { uint64 fileHandle = 1; }
        """
        return self._stub.CreateFile(arg, metadata=self.metadata)

    def CloseFile(self, arg: CloudDrive_pb2.CloseFileRequest, /) -> CloudDrive_pb2.FileOperationResult:
        """
        close an opened file

        ----------------------------------------------------------------

        rpc definition::

        // close an opened file
        rpc CloseFile(CloseFileRequest) returns (FileOperationResult) {}

        ----------------------------------------------------------------

        type definition::

        message CloseFileRequest { uint64 fileHandle = 1; }
        message FileOperationResult {
          bool success = 1;
          string errorMessage = 2;
        }
        """
        return self._stub.CloseFile(arg, metadata=self.metadata)

    def WriteToFileStream(self, arg: Iterator[CloudDrive_pb2.WriteFileRequest], /) -> CloudDrive_pb2.WriteFileResult:
        """
        write a stream to an opened file

        ----------------------------------------------------------------

        rpc definition::

        // write a stream to an opened file
        rpc WriteToFileStream(stream WriteFileRequest) returns (WriteFileResult) {}

        ----------------------------------------------------------------

        type definition::

        message WriteFileRequest {
          uint64 fileHandle = 1;
          uint64 startPos = 2;
          uint64 length = 3;
          bytes buffer = 4;
          bool closeFile = 5;
        }
        message WriteFileResult { uint64 bytesWritten = 1; }
        """
        return self._stub.WriteToFileStream(arg, metadata=self.metadata)

    def WriteToFile(self, arg: CloudDrive_pb2.WriteFileRequest, /) -> CloudDrive_pb2.WriteFileResult:
        """
        write to an opened file

        ----------------------------------------------------------------

        rpc definition::

        // write to an opened file
        rpc WriteToFile(WriteFileRequest) returns (WriteFileResult) {}

        ----------------------------------------------------------------

        type definition::

        message WriteFileRequest {
          uint64 fileHandle = 1;
          uint64 startPos = 2;
          uint64 length = 3;
          bytes buffer = 4;
          bool closeFile = 5;
        }
        message WriteFileResult { uint64 bytesWritten = 1; }
        """
        return self._stub.WriteToFile(arg, metadata=self.metadata)

    def GetPromotions(self, /) -> CloudDrive_pb2.GetPromotionsResult:
        """
        get promotions

        ----------------------------------------------------------------

        rpc definition::

        // get promotions
        rpc GetPromotions(google.protobuf.Empty) returns (GetPromotionsResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.GetPromotions(Empty(), metadata=self.metadata)

    def UpdatePromotionResult(self, /) -> None:
        """
        update promotion result after purchased

        ----------------------------------------------------------------

        rpc definition::

        // update promotion result after purchased
        rpc UpdatePromotionResult(google.protobuf.Empty) returns (google.protobuf.Empty) {}
        """
        return self._stub.UpdatePromotionResult(Empty(), metadata=self.metadata)

    def GetCloudDrivePlans(self, /) -> CloudDrive_pb2.GetCloudDrivePlansResult:
        """
        get cloudfs plans

        ----------------------------------------------------------------

        rpc definition::

        // get cloudfs plans
        rpc GetCloudDrivePlans(google.protobuf.Empty)
            returns (GetCloudDrivePlansResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.GetCloudDrivePlans(Empty(), metadata=self.metadata)

    def JoinPlan(self, arg: CloudDrive_pb2.JoinPlanRequest, /) -> CloudDrive_pb2.JoinPlanResult:
        """
        join a plan

        ----------------------------------------------------------------

        rpc definition::

        // join a plan
        rpc JoinPlan(JoinPlanRequest) returns (JoinPlanResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.JoinPlan(arg, metadata=self.metadata)

    def BindCloudAccount(self, arg: CloudDrive_pb2.BindCloudAccountRequest, /) -> None:
        """
        bind account to a cloud account id

        ----------------------------------------------------------------

        rpc definition::

        // bind account to a cloud account id
        rpc BindCloudAccount(BindCloudAccountRequest)
            returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message BindCloudAccountRequest {
          string cloudName = 1;
          string cloudAccountId = 2;
        }
        """
        return self._stub.BindCloudAccount(arg, metadata=self.metadata)

    def TransferBalance(self, arg: CloudDrive_pb2.TransferBalanceRequest, /) -> None:
        """
        transfer balance to another user

        ----------------------------------------------------------------

        rpc definition::

        //transfer balance to another user
        rpc TransferBalance(TransferBalanceRequest)
            returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message TransferBalanceRequest {
          string toUserName = 1;
          double amount = 2;
          string password = 3;
        }
        """
        return self._stub.TransferBalance(arg, metadata=self.metadata)

    def ChangeEmail(self, arg: CloudDrive_pb2.ChangeUserNameEmailRequest, /) -> None:
        """
        change email

        ----------------------------------------------------------------

        rpc definition::

        //change email
        rpc ChangeEmail(ChangeUserNameEmailRequest)
            returns (google.protobuf.Empty) {}

        ----------------------------------------------------------------

        type definition::

        message ChangeUserNameEmailRequest {
          string newUserName = 1;
          string newEmail = 2;
          string password = 3;
        }
        """
        return self._stub.ChangeEmail(arg, metadata=self.metadata)

    def GetBalanceLog(self, /) -> CloudDrive_pb2.BalanceLogResult:
        """
        chech balance log

        ----------------------------------------------------------------

        rpc definition::

        // chech balance log
        rpc GetBalanceLog(google.protobuf.Empty)
            returns (BalanceLogResult) {}

        ----------------------------------------------------------------

        type definition::

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
        message BalanceLogResult {
          repeated BalanceLog logs = 1;
        }
        """
        return self._stub.GetBalanceLog(Empty(), metadata=self.metadata)

    def CheckActivationCode(self, arg: CloudDrive_pb2.StringValue, /) -> CloudDrive_pb2.CheckActivationCodeResult:
        """
        check activation code for a plan

        ----------------------------------------------------------------

        rpc definition::

        // check activation code for a plan
        rpc CheckActivationCode(StringValue)
            returns (CheckActivationCodeResult) {}

        ----------------------------------------------------------------

        type definition::

        message CheckActivationCodeResult {
          string planId = 1;
          string planName = 2;
          string planDescription = 3;
        }
        message StringValue { string value = 1; }
        """
        return self._stub.CheckActivationCode(arg, metadata=self.metadata)

    def ActivatePlan(self, arg: CloudDrive_pb2.StringValue, /) -> CloudDrive_pb2.JoinPlanResult:
        """
        Activate plan using an activation code

        ----------------------------------------------------------------

        rpc definition::

        // Activate plan using an activation code
        rpc ActivatePlan(StringValue)
          returns (JoinPlanResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.ActivatePlan(arg, metadata=self.metadata)

    def CheckCouponCode(self, arg: CloudDrive_pb2.CheckCouponCodeRequest, /) -> CloudDrive_pb2.CouponCodeResult:
        """
        check counpon code for a plan

        ----------------------------------------------------------------

        rpc definition::

        // check counpon code for a plan
        rpc CheckCouponCode(CheckCouponCodeRequest)
            returns (CouponCodeResult) {}

        ----------------------------------------------------------------

        type definition::

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
        return self._stub.CheckCouponCode(arg, metadata=self.metadata)

    def GetReferralCode(self, /) -> CloudDrive_pb2.StringValue:
        """

        ----------------------------------------------------------------

        rpc definition::

        rpc GetReferralCode(google.protobuf.Empty)
            returns (StringValue) {}

        ----------------------------------------------------------------

        type definition::

        message StringValue { string value = 1; }
        """
        return self._stub.GetReferralCode(Empty(), metadata=self.metadata)

