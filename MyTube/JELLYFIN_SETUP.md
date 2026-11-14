# Jellyfin Setup and Migration

This guide covers the MyTube settings that must match a new Jellyfin installation.

## Find the Jellyfin IDs

Create an API key in the Jellyfin dashboard, then run these PowerShell commands on a machine that can reach the Jellyfin server. The key is prompted for and is not included in the commands:

```powershell
$server = "http://<JELLYFIN_HOST>:8096"
$token = Read-Host "Jellyfin API key"
$headers = @{ Authorization = "MediaBrowser Token=`"$token`"" }

Invoke-RestMethod "$server/Users" -Headers $headers |
    Select-Object Name, Id

Invoke-RestMethod "$server/Library/VirtualFolders" -Headers $headers |
    Select-Object Name, CollectionType, ItemId
```

Set `JELLYFIN_USER_ID` to the `Id` for the user MyTube should use. Map library `ItemId` values by name/type:

| MyTube setting | Jellyfin library |
|---|---|
| `JELLYFIN_LIBRARY_ID` | The YouTube library (`homevideos`) |
| `JELLYFIN_MOVIES_LIBRARY_ID` | The Movies library (`movies`) |
| `JELLYFIN_SHOWS_LIBRARY_ID` | The Shows library (`tvshows`) |

Set the Jellyfin URL, API key, user ID, and library IDs in `backend/config.py`, or provide the matching environment variables. Environment variables take precedence:

```powershell
$env:JELLYFIN_URL = "http://<JELLYFIN_HOST>:8096"
$env:JELLYFIN_API_KEY = "<API_KEY>"
$env:JELLYFIN_USER_ID = "<USER_ID>"
$env:JELLYFIN_LIBRARY_ID = "<YOUTUBE_LIBRARY_ID>"
$env:JELLYFIN_MOVIES_LIBRARY_ID = "<MOVIES_LIBRARY_ID>"
$env:JELLYFIN_SHOWS_LIBRARY_ID = "<SHOWS_LIBRARY_ID>"
```

The backend sends authenticated Jellyfin requests with the `Authorization: MediaBrowser Token="..."` header. Browser media requests are proxied through MyTube so HLS playlists and segments use the same authentication method. Make sure clients can reach the MyTube server over your LAN or private VPN. Keep API keys private; do not put them in documentation or commit them to source control.

## After replacing Jellyfin

1. Make sure the new Jellyfin libraries point to the existing media folders and that the selected MyTube user can access them.
2. Update the URL, API key, user ID, and library IDs above. Library IDs can change when libraries are recreated, so look them up rather than copying old values.
3. Restart MyTube so it reloads its configuration.
4. Run MyTube's library scan to refresh its SQLite catalog from Jellyfin:

   ```powershell
   Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/admin/scan"
   ```

MyTube stores Jellyfin **item IDs** in SQLite for individual videos, movies, shows, and episodes. These are different from library IDs. Do not batch-replace item IDs with library IDs or run a blind SQL update. A scan reads the new item IDs from Jellyfin and matches items to existing records; keep a backup of the database before a migration.

## IDs found on the current server

The configured server currently reports user `Xavier` and these libraries:

| User/library | ID |
|---|---|
| User `Xavier` | `05e68dd11ab249ca96eb3bd4844de2c5` |
| YouTube (`homevideos`) | `34f331a89ce405e2b877d68d5ee4d4a2` |
| Movies (`movies`) | `f137a2dd21bbc1b99aa5c0f6bf02a805` |
| Shows (`tvshows`) | `a656b907eb3a73532e40e44b968d0225` |
