{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { nixpkgs, ... }: {
    devShells.x86_64-linux.default =
      let pkgs = nixpkgs.legacyPackages.x86_64-linux;
      in pkgs.mkShell {
        packages = [
          pkgs.git
          pkgs.python311
          pkgs.python311Packages.pytest
          pkgs.ruff
          pkgs.taskwarrior3
          pkgs.ty
          pkgs.uv
        ];
        UV_NO_MANAGED_PYTHON = "1";
      };
  };
}
