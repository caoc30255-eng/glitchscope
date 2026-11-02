


    // !!! This file is generated using emlearn !!!

    #include <stdint.h>
    

static inline float oss_b_frame_correct_tree_0(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[5] < 5.500000f) {
                  return 1.000000f;
              } else {
                  if (features[4] < 20.500000f) {
                      if (features[4] < 10.500000f) {
                          return 1.000000f;
                      } else {
                          return 0.800000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[5] < 25.500000f) {
                      if (features[0] < 3.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.428571f;
                      }
                  } else {
                      return 0.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_1(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              return 1.000000f;
          } else {
              if (features[4] < 20.500000f) {
                  if (features[5] < 25.500000f) {
                      if (features[0] < 3.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.666667f;
                      }
                  } else {
                      return 0.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_2(const float *features, int32_t features_length) {
          if (features[5] < 25.500000f) {
              if (features[5] < 15.500000f) {
                  if (features[0] < 3.500000f) {
                      if (features[5] < 5.500000f) {
                          return 1.000000f;
                      } else {
                          if (features[4] < 20.500000f) {
                              return 0.857143f;
                          } else {
                              return 1.000000f;
                          }
                      }
                  } else {
                      return 1.000000f;
                  }
              } else {
                  if (features[4] < 10.500000f) {
                      return 0.000000f;
                  } else {
                      if (features[0] < 3.500000f) {
                          return 0.750000f;
                      } else {
                          return 1.000000f;
                      }
                  }
              }
          } else {
              return 0.000000f;
          }
        }
        

static inline float oss_b_frame_correct_tree_3(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[5] < 5.500000f) {
                  return 1.000000f;
              } else {
                  if (features[4] < 20.500000f) {
                      if (features[0] < 3.500000f) {
                          return 0.833333f;
                      } else {
                          return 1.000000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[4] < 10.500000f) {
                      return 0.000000f;
                  } else {
                      return 0.200000f;
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_4(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[4] < 20.500000f) {
                  if (features[0] < 3.500000f) {
                      if (features[4] < 10.500000f) {
                          return 1.000000f;
                      } else {
                          return 0.375000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[0] < 3.500000f) {
                      return 0.000000f;
                  } else {
                      if (features[5] < 25.500000f) {
                          return 0.600000f;
                      } else {
                          return 0.000000f;
                      }
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_5(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[4] < 20.500000f) {
                  if (features[0] < 3.500000f) {
                      if (features[4] < 10.500000f) {
                          return 1.000000f;
                      } else {
                          return 0.800000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[4] < 10.500000f) {
                      return 0.000000f;
                  } else {
                      if (features[5] < 25.500000f) {
                          return 0.285714f;
                      } else {
                          return 0.000000f;
                      }
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_6(const float *features, int32_t features_length) {
          if (features[5] < 25.500000f) {
              if (features[5] < 15.500000f) {
                  if (features[4] < 20.500000f) {
                      if (features[0] < 3.500000f) {
                          if (features[4] < 10.500000f) {
                              return 1.000000f;
                          } else {
                              return 0.500000f;
                          }
                      } else {
                          return 1.000000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              } else {
                  if (features[4] < 20.500000f) {
                      if (features[0] < 3.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.600000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              return 0.000000f;
          }
        }
        

static inline float oss_b_frame_correct_tree_7(const float *features, int32_t features_length) {
          if (features[5] < 25.500000f) {
              if (features[5] < 15.500000f) {
                  return 1.000000f;
              } else {
                  if (features[4] < 20.500000f) {
                      if (features[4] < 10.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.333333f;
                      }
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              return 0.000000f;
          }
        }
        

static inline float oss_b_frame_correct_tree_8(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[5] < 5.500000f) {
                  return 1.000000f;
              } else {
                  if (features[0] < 3.500000f) {
                      if (features[4] < 20.500000f) {
                          return 0.833333f;
                      } else {
                          return 1.000000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[4] < 10.500000f) {
                      return 0.000000f;
                  } else {
                      if (features[0] < 3.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.285714f;
                      }
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_9(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[0] < 3.500000f) {
                  if (features[5] < 5.500000f) {
                      return 1.000000f;
                  } else {
                      return 0.857143f;
                  }
              } else {
                  return 1.000000f;
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[0] < 3.500000f) {
                      return 0.000000f;
                  } else {
                      if (features[4] < 10.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.333333f;
                      }
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_10(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[0] < 3.500000f) {
                  if (features[5] < 5.500000f) {
                      return 1.000000f;
                  } else {
                      return 0.714286f;
                  }
              } else {
                  return 1.000000f;
              }
          } else {
              if (features[4] < 20.500000f) {
                  return 0.000000f;
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_11(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[4] < 20.500000f) {
                  if (features[0] < 3.500000f) {
                      return 0.571429f;
                  } else {
                      return 1.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[5] < 25.500000f) {
                      if (features[4] < 10.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.250000f;
                      }
                  } else {
                      return 0.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_12(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[4] < 20.500000f) {
                  if (features[5] < 5.500000f) {
                      return 1.000000f;
                  } else {
                      if (features[4] < 10.500000f) {
                          return 1.000000f;
                      } else {
                          return 0.800000f;
                      }
                  }
              } else {
                  return 1.000000f;
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[4] < 10.500000f) {
                      return 0.000000f;
                  } else {
                      if (features[5] < 25.500000f) {
                          return 0.400000f;
                      } else {
                          return 0.000000f;
                      }
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_13(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              return 1.000000f;
          } else {
              if (features[4] < 10.500000f) {
                  return 0.000000f;
              } else {
                  if (features[5] < 25.500000f) {
                      return 0.777778f;
                  } else {
                      return 0.000000f;
                  }
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_14(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[0] < 3.500000f) {
                  if (features[5] < 5.500000f) {
                      return 1.000000f;
                  } else {
                      if (features[4] < 20.500000f) {
                          return 0.750000f;
                      } else {
                          return 1.000000f;
                      }
                  }
              } else {
                  return 1.000000f;
              }
          } else {
              if (features[4] < 20.500000f) {
                  return 0.000000f;
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_15(const float *features, int32_t features_length) {
          if (features[5] < 25.500000f) {
              if (features[5] < 15.500000f) {
                  if (features[4] < 20.500000f) {
                      if (features[0] < 3.500000f) {
                          return 0.800000f;
                      } else {
                          return 1.000000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              } else {
                  if (features[4] < 10.500000f) {
                      return 0.000000f;
                  } else {
                      if (features[0] < 3.500000f) {
                          return 0.333333f;
                      } else {
                          return 1.000000f;
                      }
                  }
              }
          } else {
              return 0.000000f;
          }
        }
        

static inline float oss_b_frame_correct_tree_16(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[4] < 20.500000f) {
                  if (features[0] < 3.500000f) {
                      if (features[4] < 10.500000f) {
                          return 1.000000f;
                      } else {
                          return 0.800000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[5] < 25.500000f) {
                      if (features[0] < 3.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.200000f;
                      }
                  } else {
                      return 0.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_17(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[5] < 5.500000f) {
                  return 1.000000f;
              } else {
                  if (features[0] < 3.500000f) {
                      if (features[4] < 20.500000f) {
                          return 0.800000f;
                      } else {
                          return 1.000000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[5] < 25.500000f) {
                      if (features[4] < 10.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.400000f;
                      }
                  } else {
                      return 0.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_18(const float *features, int32_t features_length) {
          if (features[5] < 25.500000f) {
              if (features[5] < 15.500000f) {
                  if (features[0] < 3.500000f) {
                      if (features[5] < 5.500000f) {
                          return 1.000000f;
                      } else {
                          if (features[4] < 20.500000f) {
                              return 0.750000f;
                          } else {
                              return 1.000000f;
                          }
                      }
                  } else {
                      return 1.000000f;
                  }
              } else {
                  if (features[4] < 20.500000f) {
                      if (features[4] < 10.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.500000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              return 0.000000f;
          }
        }
        

static inline float oss_b_frame_correct_tree_19(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[5] < 5.500000f) {
                  return 1.000000f;
              } else {
                  if (features[0] < 3.500000f) {
                      return 0.875000f;
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              if (features[5] < 25.500000f) {
                  return 0.307692f;
              } else {
                  return 0.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_20(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              return 1.000000f;
          } else {
              if (features[4] < 20.500000f) {
                  if (features[4] < 10.500000f) {
                      return 0.000000f;
                  } else {
                      if (features[0] < 3.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.500000f;
                      }
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_21(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              return 1.000000f;
          } else {
              if (features[4] < 20.500000f) {
                  if (features[4] < 10.500000f) {
                      return 0.000000f;
                  } else {
                      if (features[0] < 3.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.250000f;
                      }
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_22(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[5] < 5.500000f) {
                  return 1.000000f;
              } else {
                  if (features[4] < 20.500000f) {
                      if (features[0] < 3.500000f) {
                          return 0.600000f;
                      } else {
                          return 1.000000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[5] < 25.500000f) {
                      if (features[4] < 10.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.250000f;
                      }
                  } else {
                      return 0.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_23(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              return 1.000000f;
          } else {
              if (features[4] < 20.500000f) {
                  if (features[4] < 10.500000f) {
                      return 0.000000f;
                  } else {
                      return 0.200000f;
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_24(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[5] < 5.500000f) {
                  return 1.000000f;
              } else {
                  if (features[0] < 3.500000f) {
                      if (features[4] < 20.500000f) {
                          if (features[4] < 10.500000f) {
                              return 1.000000f;
                          } else {
                              return 0.800000f;
                          }
                      } else {
                          return 1.000000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              if (features[4] < 20.500000f) {
                  return 0.000000f;
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_25(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[4] < 20.500000f) {
                  if (features[4] < 10.500000f) {
                      return 1.000000f;
                  } else {
                      return 0.888889f;
                  }
              } else {
                  return 1.000000f;
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[4] < 10.500000f) {
                      return 0.000000f;
                  } else {
                      return 0.125000f;
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_26(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              return 1.000000f;
          } else {
              if (features[4] < 10.500000f) {
                  return 0.000000f;
              } else {
                  if (features[5] < 25.500000f) {
                      if (features[0] < 3.500000f) {
                          return 0.166667f;
                      } else {
                          return 1.000000f;
                      }
                  } else {
                      return 0.000000f;
                  }
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_27(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[5] < 5.500000f) {
                  return 1.000000f;
              } else {
                  if (features[4] < 20.500000f) {
                      if (features[4] < 10.500000f) {
                          return 1.000000f;
                      } else {
                          return 0.666667f;
                      }
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[5] < 25.500000f) {
                      if (features[0] < 3.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.428571f;
                      }
                  } else {
                      return 0.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_28(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[4] < 20.500000f) {
                  if (features[0] < 3.500000f) {
                      if (features[4] < 10.500000f) {
                          return 1.000000f;
                      } else {
                          return 0.714286f;
                      }
                  } else {
                      return 1.000000f;
                  }
              } else {
                  return 1.000000f;
              }
          } else {
              if (features[4] < 20.500000f) {
                  if (features[0] < 3.500000f) {
                      return 0.000000f;
                  } else {
                      if (features[5] < 25.500000f) {
                          return 0.200000f;
                      } else {
                          return 0.000000f;
                      }
                  }
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_29(const float *features, int32_t features_length) {
          if (features[5] < 15.500000f) {
              if (features[5] < 5.500000f) {
                  return 1.000000f;
              } else {
                  if (features[0] < 3.500000f) {
                      return 0.625000f;
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              if (features[4] < 20.500000f) {
                  return 0.000000f;
              } else {
                  return 1.000000f;
              }
          }
        }
        

static inline float oss_b_frame_correct_tree_30(const float *features, int32_t features_length) {
          if (features[5] < 25.500000f) {
              if (features[5] < 15.500000f) {
                  if (features[0] < 3.500000f) {
                      if (features[4] < 20.500000f) {
                          if (features[4] < 10.500000f) {
                              return 1.000000f;
                          } else {
                              return 0.666667f;
                          }
                      } else {
                          return 1.000000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              } else {
                  if (features[4] < 20.500000f) {
                      if (features[0] < 3.500000f) {
                          return 0.000000f;
                      } else {
                          return 0.250000f;
                      }
                  } else {
                      return 1.000000f;
                  }
              }
          } else {
              return 0.000000f;
          }
        }
        

static const uint8_t oss_b_frame_correct_leaves[100] = { 0, 0, 128, 63, 205, 204, 76, 63, 0, 0, 0, 0, 183, 109, 219, 62, 171, 170, 42, 63, 183, 109, 91, 63, 0, 0, 64, 63, 85, 85, 85, 63, 205, 204, 76, 62, 0, 0, 192, 62, 154, 153, 25, 63, 37, 73, 146, 62, 0, 0, 0, 63, 171, 170, 170, 62, 110, 219, 54, 63, 37, 73, 18, 63, 0, 0, 128, 62, 205, 204, 204, 62, 114, 28, 71, 63, 0, 0, 96, 63, 217, 137, 157, 62, 57, 142, 99, 63, 0, 0, 0, 62, 171, 170, 42, 62, 0, 0, 32, 63 };

float oss_b_frame_correct_predict(const float *features, int32_t features_length) {

        float avg = 0;

        avg += oss_b_frame_correct_tree_0(features, features_length); 
    avg += oss_b_frame_correct_tree_1(features, features_length); 
    avg += oss_b_frame_correct_tree_2(features, features_length); 
    avg += oss_b_frame_correct_tree_3(features, features_length); 
    avg += oss_b_frame_correct_tree_4(features, features_length); 
    avg += oss_b_frame_correct_tree_5(features, features_length); 
    avg += oss_b_frame_correct_tree_6(features, features_length); 
    avg += oss_b_frame_correct_tree_7(features, features_length); 
    avg += oss_b_frame_correct_tree_8(features, features_length); 
    avg += oss_b_frame_correct_tree_9(features, features_length); 
    avg += oss_b_frame_correct_tree_10(features, features_length); 
    avg += oss_b_frame_correct_tree_11(features, features_length); 
    avg += oss_b_frame_correct_tree_12(features, features_length); 
    avg += oss_b_frame_correct_tree_13(features, features_length); 
    avg += oss_b_frame_correct_tree_14(features, features_length); 
    avg += oss_b_frame_correct_tree_15(features, features_length); 
    avg += oss_b_frame_correct_tree_16(features, features_length); 
    avg += oss_b_frame_correct_tree_17(features, features_length); 
    avg += oss_b_frame_correct_tree_18(features, features_length); 
    avg += oss_b_frame_correct_tree_19(features, features_length); 
    avg += oss_b_frame_correct_tree_20(features, features_length); 
    avg += oss_b_frame_correct_tree_21(features, features_length); 
    avg += oss_b_frame_correct_tree_22(features, features_length); 
    avg += oss_b_frame_correct_tree_23(features, features_length); 
    avg += oss_b_frame_correct_tree_24(features, features_length); 
    avg += oss_b_frame_correct_tree_25(features, features_length); 
    avg += oss_b_frame_correct_tree_26(features, features_length); 
    avg += oss_b_frame_correct_tree_27(features, features_length); 
    avg += oss_b_frame_correct_tree_28(features, features_length); 
    avg += oss_b_frame_correct_tree_29(features, features_length); 
    avg += oss_b_frame_correct_tree_30(features, features_length); 
        
        return avg/31;
    }
    