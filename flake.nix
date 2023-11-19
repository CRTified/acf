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
            (final: prev: {
              pari-seadata = prev.pari-seadata-small.overrideAttrs (old: {
                pname = "pari-seadata";
                src = prev.fetchzip {
                  url = "https://pari.math.u-bordeaux.fr/pub/pari/packages/seadata.tgz";
                  hash = "sha256-WBxYkligfYCU01dLokThdEliMZBt/eehDn6v9AET8co=";
                };
              });
              pari-seadata-big = prev.pari-seadata-small.overrideAttrs (old: {
                pname = "pari-seadata-big";
                src = prev.fetchzip {
                  url = "https://pari.math.u-bordeaux.fr/pub/pari/packages/seadata-big.tar";
                  hash = "sha256-fE2yYkgIpbvSugD4tkSkOfBQhTLv1oCiR2EP3VgipfI=";
                };
              });
            })

            # We don't need to run the sage tests here
            (final: prev: {
              sage = prev.sage.override {
                requireSageTests = false;
                extraPythonPackages = ps: with ps; [ ];
              };
            })
          ];
        };

        python3 = pkgs.python3.withPackages (ps: with ps; [ cypari2 ]);

        curve_finder = pkgs.writeScriptBin "curve_finder.py"
          (builtins.readFile ./curve_finder.py);

      in {
        packages = {
          inherit (pkgs) sage pari-seadata;
          inherit python3;

          oci-acf-py = pkgs.dockerTools.buildImage {
            name = "acf-py";
            tag = "latest";
            copyToRoot = [ python3 pkgs.pari-seadata curve_finder ];

            runAsRoot = ''
              #!${pkgs.runtimeShell}
              mkdir -p /data
              mkdir -p /tmp
            '';

            config = {
              Env = [
                "GP_DATA_DIR=${pkgs.pari-seadata}/share/pari"
              ];
              Cmd = [
                "${python3}/bin/python3"
                "${curve_finder}/bin/curve_finder.py"
                "--coordinator"
              ];
              WorkingDir = "/data";
              Volumes = { "/data" = { }; };
            };
          };
          oci-acf-sage = pkgs.dockerTools.buildImage {
            name = "acf-sage";
            tag = "latest";
            copyToRoot = [ pkgs.coreutils pkgs.gnused pkgs.sage curve_finder ];

            runAsRoot = ''
              #!${pkgs.runtimeShell}
              mkdir -p /data
              mkdir -p /tmp
            '';

            config = {
              Cmd = [
                "${pkgs.sage}/bin/sage"
                "${curve_finder}/bin/curve_finder.py"
                "--coordinator"
              ];
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
