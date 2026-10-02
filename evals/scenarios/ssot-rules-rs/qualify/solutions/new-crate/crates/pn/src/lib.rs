//! The club's Portsmouth Numbers: the RYA list for 2026, plus the club's own number for the Feva XL. Class
//! names exactly as race files write them. Update every March, when the RYA publishes the new list.

pub static PN_2026: [(&str, u32); 16] = [
    ("Comet", 1_210), ("Enterprise", 1_116), ("Finn", 1_049), ("GP14", 1_130),
    ("ILCA 4", 1_207), ("ILCA 6", 1_147), ("ILCA 7", 1_100), ("Mirror", 1_386),
    ("Optimist", 1_642), ("RS Aero 7", 1_063), ("RS Feva XL", 1_240), ("RS200", 1_047),
    ("RS400", 942), ("Solo", 1_142), ("Topper", 1_364), ("Wayfarer", 1_102),
];

/// The Portsmouth Number for a class, if the club has one.
pub fn lookup(class: &str) -> Option<u32> {
    PN_2026.iter().find(|(name, _)| *name == class).map(|&(_, pn)| pn)
}
