{
  config,
  pkgs,
  lib,
  ...
}:
{
  systemd.paths = lib.mapAttrs' (name: val: {
    name = "${name}-key";
    value = {
      wantedBy = [ "paths.target" ];
      pathConfig = {
        PathExists = val.path;
      };
    };
  }) config.deployment.keys;

  systemd.services = lib.mapAttrs' (name: val: {
    name = "${name}-key";
    value = {
      enable = true;
      serviceConfig = {
        TimeoutStartSec = "infinity";
        Restart = "always";
        RestartSec = "100ms";
      };
      path = [ pkgs.inotify-tools ];
      preStart = ''
        (while read f; do if [ "$f" = "${val.name}" ]; then break; fi; done \
          < <(inotifywait -qm --format '%f' -e create,move ${val.destDir}) ) &
        if [[ -e "${val.path}" ]]; then
          echo 'flapped down'
          kill %1
          exit 0
        fi
        wait %1
      '';
      script = ''
        inotifywait -qq -e delete_self "${val.path}" &
        if [[ ! -e "${val.path}" ]]; then
          echo 'flapped up'
          exit 0
        fi
        wait %1
      '';
    };
  }) config.deployment.keys;
}
