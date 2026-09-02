{
  description = "dots.mocr gateway development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          python312
          uv
          nodejs_24
          gnumake
          ruff
        ];

        LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
          pkgs.stdenv.cc.cc.lib
          pkgs.zlib
        ];

        shellHook = ''
          export UV_PYTHON=${pkgs.python312}/bin/python3
          export UV_PYTHON_DOWNLOADS=never
        '';
      };

      formatter.${system} = pkgs.nixfmt;
    };
}
