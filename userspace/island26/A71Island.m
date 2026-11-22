// A71Island: SpringBoard geometry for the system Dynamic Island on the Galaxy A71 (iOS 26.6.2, 23G90).
//
// The island code is in every iOS 26 SpringBoard; it turns on for MobileGestalt ArtworkDeviceSubType 2556
// (iPhone 14 Pro). That subtype alone gave the A71 a red status bar: UIKit then expects an exclusion area that the
// iPhone 11 screen type (414x896 pt) does not have. SpringBoard computes the geometry once and hands it to every app
// (UISDisplayContext), so these hooks run in SpringBoard only:
//   +[UISDisplaySingleRectShape sb_displayShapeForScreenType:]  exclusion area (points) -> DynamicSplit status bar
//   -[SBUISystemApertureLayoutMetrics sensorRegionSize]          size of the pill; compact/minimal sizes derive from it
//   -[SBUISystemApertureLayoutMetrics minimumScreenEdgeInsets]   top gap of the pill
//   -[SBUISystemApertureLayoutMetrics interSensorRegionInWindowSpace]  privacy dot position
//   +[SBHDefaultIconListLayoutProvider currentDeviceScreenType]  optional (HomeScreenType > 0): home grid type
// Approach after Viva's SpringBoard display hooks (Redmi Note 11 Pro 4G, github.com/nik300/viva-gpu); own code.
//
// Loaded by an extra LC_LOAD_DYLIB in SpringBoard (re-signed ad hoc, identifier and entitlements kept).
// Preferences: /var/mobile/Library/Preferences/org.a71.island.plist, every number optional; Enabled = NO disables.
// Log: os_log subsystem org.a71.island (reaches the USB console with sweetdtlog=SpringBoard).
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <os/log.h>

static os_log_t ILog;
#define ILOG(fmt, ...) os_log(ILog, "A71ISLAND " fmt, ##__VA_ARGS__)

// Points on the 414x896 pt screen. Apple's 2556 pill is 125 x 36.67 pt at 11.33 pt from the top; the A71 punch hole
// sits at the top centre, inside that box.
static double IScreenW = 414.0;
static double IIslandW = 125.0, IIslandH = 36.667, IIslandTop = 11.333;
static double IAvoidW = 150.0;     // status bar keeps this width free around the pill
static double IInterW = 9.0;       // privacy dot slot
static long IHomeType = 0;         // 0 = SpringBoard's own

static IMP IOrigInsets, IOrigHomeType;

static double INum(NSDictionary *d, NSString *k, double def) {
    id v = d[k];
    return [v respondsToSelector:@selector(doubleValue)] ? [v doubleValue] : def;
}

static BOOL IHook(NSString *cls, SEL sel, BOOL meta, id block, IMP *orig) {
    Class c = NSClassFromString(cls);
    if (c && meta) c = object_getClass(c);
    Method m = c ? class_getInstanceMethod(c, sel) : NULL;
    if (!m) {
        ILOG("hook missing: %{public}@ %{public}s", cls, sel_getName(sel));
        return NO;
    }
    IMP old = method_setImplementation(m, imp_implementationWithBlock(block));
    if (orig) *orig = old;
    ILOG("hooked %{public}@ %{public}s", cls, sel_getName(sel));
    return YES;
}

static void IInstall(void) {
    IHook(@"SBUISystemApertureLayoutMetrics", @selector(sensorRegionSize), NO, ^CGSize(id self) {
        return CGSizeMake(IIslandW, IIslandH);
    }, NULL);
    IHook(@"SBUISystemApertureLayoutMetrics", @selector(minimumScreenEdgeInsets), NO, ^NSDirectionalEdgeInsets(id self) {
        NSDirectionalEdgeInsets i = ((NSDirectionalEdgeInsets (*)(id, SEL))IOrigInsets)(self, @selector(minimumScreenEdgeInsets));
        i.top = IIslandTop;
        return i;
    }, &IOrigInsets);
    IHook(@"SBUISystemApertureLayoutMetrics", @selector(interSensorRegionInWindowSpace), NO, ^CGRect(id self) {
        return CGRectMake(IScreenW / 2 - IInterW / 2, IIslandTop, IInterW, IIslandH);
    }, NULL);
    IHook(@"UISDisplaySingleRectShape", NSSelectorFromString(@"sb_displayShapeForScreenType:"), YES, ^id(id self, NSInteger type) {
        double w = MAX(IAvoidW, IIslandW);
        CGRect r = CGRectMake(IScreenW / 2 - w / 2, IIslandTop, w, IIslandH);
        ILOG("display shape for screen type %ld -> %{public}@", (long)type, NSStringFromCGRect(r));
        id (*init)(id, SEL, CGRect) = (id (*)(id, SEL, CGRect))objc_msgSend;
        return init([NSClassFromString(@"UISDisplaySingleRectShape") alloc], @selector(initWithRect:), r);
    }, NULL);
    IHook(@"SBHDefaultIconListLayoutProvider", NSSelectorFromString(@"currentDeviceScreenType"), YES, ^unsigned long(id self) {
        unsigned long own = ((unsigned long (*)(id, SEL))IOrigHomeType)(self, NSSelectorFromString(@"currentDeviceScreenType"));
        static dispatch_once_t once;
        dispatch_once(&once, ^{ ILOG("home screen type %lu (override %ld)", own, IHomeType); });
        return IHomeType > 0 ? (unsigned long)IHomeType : own;
    }, &IOrigHomeType);
}

__attribute__((constructor)) static void IInit(void) {
    @autoreleasepool {
        ILog = os_log_create("org.a71.island", "tweak");
        if (strcmp(getprogname(), "SpringBoard") != 0) return;
        NSDictionary *p = [NSDictionary dictionaryWithContentsOfFile:@"/var/mobile/Library/Preferences/org.a71.island.plist"];
        if (p[@"Enabled"] && ![p[@"Enabled"] boolValue]) {
            ILOG("disabled by preference");
            return;
        }
        IScreenW = INum(p, @"ScreenWidth", IScreenW);
        IIslandW = INum(p, @"IslandWidth", IIslandW);
        IIslandH = INum(p, @"IslandHeight", IIslandH);
        IIslandTop = INum(p, @"IslandTop", IIslandTop);
        IAvoidW = INum(p, @"StatusBarAvoidWidth", IAvoidW);
        IHomeType = (long)INum(p, @"HomeScreenType", IHomeType);
        @try {
            IInstall();
        } @catch (NSException *e) {
            ILOG("install: %{public}@", e);
        }
        ILOG("active: pill %.2fx%.2f at %.2f pt on %.0f pt", IIslandW, IIslandH, IIslandTop, IScreenW);
    }
}
