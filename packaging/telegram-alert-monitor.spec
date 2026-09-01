Name:           telegram-alert-monitor
Version:         %{app_version}
Release:         1%{?dist}
Summary:         Telegram Alert Monitor desktop and daemon application
License:         Proprietary
BuildArch:       x86_64
AutoReqProv:     no

Source0:         TelegramAlertMonitor
Source1:         config.example.toml
Source2:         telegram-alert-monitor.service
Source3:         environment.example
Source4:         README-deb.md

%description
Telegram Alert Monitor monitors configured Telegram channels and can run as a desktop application or daemon.

%prep

%build

%install
rm -rf %{buildroot}
install -d %{buildroot}%{_libexecdir}/telegram-alert-monitor %{buildroot}%{_bindir} %{buildroot}%{_sysconfdir}/telegram-alert-monitor %{buildroot}%{_unitdir}
cp -a %{_sourcedir}/TelegramAlertMonitor/. %{buildroot}%{_libexecdir}/telegram-alert-monitor/
ln -s %{_libexecdir}/telegram-alert-monitor/TelegramAlertMonitor %{buildroot}%{_bindir}/telegram-alert-monitor
install -m 0644 %{_sourcedir}/config.example.toml %{buildroot}%{_sysconfdir}/telegram-alert-monitor/config.example.toml
install -m 0644 %{_sourcedir}/environment.example %{buildroot}%{_sysconfdir}/telegram-alert-monitor/environment.example
install -m 0644 %{_sourcedir}/README-deb.md %{buildroot}%{_libexecdir}/telegram-alert-monitor/README-deb.md
install -m 0644 %{_sourcedir}/telegram-alert-monitor.service %{buildroot}%{_unitdir}/telegram-alert-monitor.service

%pre
getent group telegram-monitor >/dev/null || groupadd -r telegram-monitor
getent passwd telegram-monitor >/dev/null || useradd -r -g telegram-monitor -d /var/lib/telegram-alert-monitor -s /sbin/nologin telegram-monitor

%post
mkdir -p /var/lib/telegram-alert-monitor/state
chown -R telegram-monitor:telegram-monitor /var/lib/telegram-alert-monitor
systemctl daemon-reload >/dev/null 2>&1 || :

%files
%{_libexecdir}/telegram-alert-monitor
%{_bindir}/telegram-alert-monitor
%dir %{_sysconfdir}/telegram-alert-monitor
%config(noreplace) %{_sysconfdir}/telegram-alert-monitor/config.example.toml
%config(noreplace) %{_sysconfdir}/telegram-alert-monitor/environment.example
%{_libexecdir}/telegram-alert-monitor/README-deb.md
%{_unitdir}/telegram-alert-monitor.service

%changelog
