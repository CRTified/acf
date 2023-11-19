{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/master";
    flake-utils.url = "github:numtide/flake-utils";
  };
  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs.outPath {
          # Set local system
          localSystem = { inherit system; };

          overlays = [
            # We don't need to run the sage tests here
            (final: prev: {
              sage = prev.sage.override {
                requireSageTests = false;
                extraPythonPackages = ps: with ps; [ ];
              };
            })
          ];
        };

        curve_finder = pkgs.writeScriptBin "curve_finder.py"
          (builtins.readFile ./curve_finder.py);

      in {
        packages = {
          inherit (pkgs) sage;
          oci = pkgs.dockerTools.buildImage {
            name = "acf";
            tag = "latest";
            copyToRoot = [ pkgs.coreutils pkgs.gnused pkgs.sage curve_finder ];

            runAsRoot = ''
              #!${pkgs.runtimeShell}
              mkdir -p /data
              mkdir -p /tmp
            '';

            config = {
              Cmd = [ "${pkgs.sage}/bin/sage" "${curve_finder}/bin/curve_finder.py" "--coordinator" ];
              WorkingDir = "/data";
              Volumes = { "/data" = { }; };
            };
          };
        };

        apps = {
          default = self.apps."${system}".sage;
          sage = {
            type = "app";
            program = "${pkgs.sage}/bin/sage";
          };
          notebook = {
            type = "app";
            program = toString (pkgs.writeScript "sage-notebook" ''
              ${pkgs.sage}/bin/sage --notebook
            '');
          };
        };
      });
}
