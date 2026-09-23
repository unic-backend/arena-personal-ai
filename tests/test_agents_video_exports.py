def test_video_package_exposes_agnes_production_bridge():
    from agents.video import AgnesProductionBridge

    assert AgnesProductionBridge.name == "agnes_video"
