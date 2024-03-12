{ tf, outputs, resources, lib, ... }:
let
  nodes' = lib.filterAttrs (_: node: node.targetEnv == "digitalocean") (outputs.teraflops.nodes or {});
in
{
  defaults = {
    imports = [ ./digitalocean.nix ];
  };

  terraform = {
    required_providers = {
      digitalocean = {
        source = "digitalocean/digitalocean";
        version = ">= 2.32.0";
      };
    };
  };

  resource = { nodes, pkgs, lib, ... }: with lib;
    let
      nodes' = filterAttrs (_: node: node.config.deployment.targetEnv == "digitalocean") nodes;
      data = foldr (a: b: a // b) {} (attrValues (mapAttrs dataFn nodes'));
      dataFn = name: node: mapAttrs' (_: fs: nameValuePair fs.digitalocean.name {
        inherit (fs) digitalocean;

        droplet = name;
      }) (filterAttrs (_: fs: fs.digitalocean != null) node.config.fileSystems);
    in
    {
      digitalocean_droplet = mapAttrs (_: node: node.config.deployment.digitalocean) nodes';

      digitalocean_volume = mapAttrs (_: data: data.digitalocean) data;
      digitalocean_volume_attachment = mapAttrs' (name: data: nameValuePair "${name}-on-${data.droplet}" {
        droplet_id = tf.ref "digitalocean_droplet.${data.droplet}.id";
        volume_id = tf.ref "digitalocean_volume.${name}.id";
      }) data;

      # HACK: account for an incomplete terraform provider
      #
      # it should be relatively easy to extend the existing terraform provider to
      # include this information
      #
      # see https://github.com/digitalocean/terraform-provider-digitalocean/issues/1097
      ssh_resource = mapAttrs (name: node: {
        user = node.config.deployment.targetUser;
        host = node.config.deployment.targetHost;
        port = mkIf (node.config.deployment.targetPort != null) node.config.deployment.targetPort;
        private_key = mkIf node.config.deployment.provisionSSHKey (tf.ref "tls_private_key.teraflops.private_key_openssh");

        commands = [
          "curl -fsSL http://169.254.169.254/metadata/v1.json"
        ];

        depends_on = [
          "digitalocean_droplet.${name}"
        ];
      }) nodes';
    };
} // lib.mapAttrs (_: node: { modulesPath, ... }: {
  imports = [ "${modulesPath}/profiles/qemu-guest.nix" ];
}) nodes'
