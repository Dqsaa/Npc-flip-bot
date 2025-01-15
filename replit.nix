{ pkgs }: {
  deps = [
    pkgs.geckodriver
    pkgs.ungoogled-chromium
    pkgs.chromedriver
  ];
}