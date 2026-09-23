def test_video_package_exports_agnes_and_native_tools():
    from tools.video import AgnesVideoProvider, ArenaVideoOrchestrator, FFmpegTool

    assert AgnesVideoProvider.name == "agnes"
    assert ArenaVideoOrchestrator is not None
    assert FFmpegTool is not None
