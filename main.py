import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from lsync.ui.app import main

    main()
