{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { nixpkgs, pyproject-nix, uv2nix, pyproject-build-systems, ... }:
    let
      inherit (nixpkgs) lib;
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      python = pkgs.python311;
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

      baseOverlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };

      pythonBase = pkgs.callPackage pyproject-nix.build.packages {
        inherit python;
      };

      pythonSet = pythonBase.overrideScope (
        lib.composeManyExtensions [
          pyproject-build-systems.overlays.wheel
          baseOverlay
        ]
      );

      taskx = pythonSet.mkVirtualEnv "taskx-env" workspace.deps.default;
    in {
      packages.${system} = {
        inherit taskx;
        default = taskx;
      };

      apps.${system}.taskx = {
        type = "app";
        program = "${taskx}/bin/taskx";
      };

      devShells.${system}.default =
        pkgs.mkShell {
        packages = [
          pkgs.git
          pkgs.python311
          pkgs.ruff
          pkgs.taskwarrior3
          pkgs.ty
          pkgs.uv
        ];
        UV_NO_MANAGED_PYTHON = "1";
      };
  };
}
