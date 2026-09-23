def test_video_toolbox_exposes_agnes_production_bridge():
    from tools.video import AgnesProductionBridge

    assert AgnesProductionBridge.name == "agnes_video"
