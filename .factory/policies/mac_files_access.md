# Mac Files Access From Home

Goal: allow the trusted `home` server to reach the Mac through a reverse SSH
tunnel without opening Mac SSH to the public internet.

Tunnel:

```text
home:10.99.0.1:22220 -> mac:127.0.0.1:22
home:172.17.0.1:22220 -> mac:127.0.0.1:22
```

From `home`, after macOS Remote Login is enabled:

```bash
ssh -p 22220 kolibri@10.99.0.1
ssh -p 22220 kolibri@172.17.0.1
sftp -P 22220 kolibri@10.99.0.1
rsync -e 'ssh -p 22220' -az kolibri@10.99.0.1:/Users/kolibri/Documents/Codex/kolibri-ai-platform/ /srv/kolibri/repo/
```

Required Mac prerequisite:

```bash
sudo systemsetup -setremotelogin on
```

On macOS 26, `systemsetup -setremotelogin on` may require Full Disk Access.
If SSH connects but cannot read protected folders such as `~/Documents`, grant
Full Disk Access manually in:

```text
System Settings -> Privacy & Security -> Full Disk Access
```

Add or enable:

```text
/usr/libexec/sshd-keygen-wrapper
```

After that, verify from `home`:

```bash
ssh -p 22220 kolibri@10.99.0.1 'ls -la /Users/kolibri/Documents/Codex/kolibri-ai-platform'
```

Do not copy secrets into Git or factory logs.
